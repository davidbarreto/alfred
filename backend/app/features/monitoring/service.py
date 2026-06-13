from starlette.concurrency import run_in_threadpool
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

import logging
import requests

from bs4 import BeautifulSoup
from app.features.monitoring.repository import (
    create_execution,
    get_active_monitors,
    get_monitor,
    upsert_alert,
)
from app.features.monitoring.tables import Execution, Monitor
from app.integrations.http.pagination import paginate
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)


def _derive_status(raw: dict) -> tuple[str, str | None, str | None]:
    """Return (status, result, error) from a raw check result dict."""
    if raw.get("error"):
        return "error", None, raw["error"]
    if raw.get("found"):
        return "found", raw.get("matched_content"), None
    return "not_found", None, None


class MonitorService:
    @staticmethod
    def check_html_static(
        url: str,
        selector: str,
        target: str,
        case_sensitive: bool = True,
        timeout: int = 10,
    ) -> dict:
        result = {
            "found": False,
            "matched_content": None,
            "error": None,
        }

        try:
            headers = {"User-Agent": "Mozilla/5.0 (alfred/1.0)"}
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            result["error"] = f"Request failed: {exc}"
            logger.debug("Request failed for %s: %s", url, exc)
            return result

        logger.debug(
            "Fetched URL %s status=%s html_length=%d",
            url,
            getattr(response, "status_code", None),
            len(response.text or ""),
        )

        soup = BeautifulSoup(response.text, "html.parser")
        elements = soup.select(selector)

        logger.debug("Selector '%s' matched %d elements for %s", selector, len(elements), url)

        if not elements:
            result["error"] = f"No elements matched selector '{selector}'"
            return result

        needle = target if case_sensitive else target.lower()
        for element in elements:
            text = element.get_text(separator=" ", strip=True)
            haystack = text if case_sensitive else text.lower()
            if needle in haystack:
                result["found"] = True
                result["matched_content"] = text[:500]
                break

        return result

    @staticmethod
    def check_html_javascript(
        url: str,
        selector: str,
        target: str,
        case_sensitive: bool = True,
        timeout: int = 10,
        wait_selector: str | None = None,
    ) -> dict:
        result = {
            "found": False,
            "matched_content": None,
            "error": None,
        }

        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (alfred/1.0)")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            try:
                driver.set_page_load_timeout(timeout)
                driver.get(url)

                selector_to_wait = wait_selector or selector
                if selector_to_wait:
                    try:
                        WebDriverWait(driver, timeout).until(
                            EC.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, selector_to_wait)
                            )
                        )
                    except Exception as wait_exc:
                        logger.debug(
                            "Timeout waiting for selector '%s': %s", selector_to_wait, wait_exc
                        )

                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                logger.debug(
                    "Selector '%s' matched %d elements for %s (JS-rendered)",
                    selector,
                    len(elements),
                    url,
                )

                if not elements:
                    result["error"] = f"No elements matched selector '{selector}' after JS rendering"
                    return result

                needle = target if case_sensitive else target.lower()
                for element in elements:
                    try:
                        text = element.text
                        haystack = text if case_sensitive else text.lower()
                        if needle in haystack:
                            result["found"] = True
                            result["matched_content"] = text[:500]
                            break
                    except Exception as e:
                        logger.debug("Error reading element text: %s", e)

                return result

            finally:
                driver.quit()

        except ImportError:
            result["error"] = "Selenium not installed. Install with: pip install selenium webdriver-manager"
            logger.error("Selenium not available for JavaScript rendering")
            return result
        except Exception as exc:
            result["error"] = f"JavaScript rendering failed: {exc}"
            logger.debug("JS rendering failed for %s: %s", url, exc)
            return result

    @staticmethod
    def check_api(
        url: str,
        json_path: str,
        target: str,
        case_sensitive: bool = True,
        timeout: int = 10,
        page_size: int = 32,
        max_pages: int | None = None,
        request_delay: float = 0.0,
    ) -> dict:
        result = {
            "found": False,
            "matched_content": None,
            "error": None,
        }

        def _find_match(obj: Any, needle: str) -> str | None:
            """Recursively search obj; return the matched string or None."""
            if isinstance(obj, dict):
                for v in obj.values():
                    match = _find_match(v, needle)
                    if match is not None:
                        return match
                return None
            if isinstance(obj, list):
                for item in obj:
                    match = _find_match(item, needle)
                    if match is not None:
                        return match
                return None
            text = str(obj) if obj is not None else ""
            haystack = text if case_sensitive else text.lower()
            return text[:500] if needle in haystack else None

        try:
            needle = target if case_sensitive else target.lower()
            total_items_checked = 0

            try:
                for page_content in paginate(
                    url,
                    page_size=page_size,
                    delay=request_delay,
                    max_pages=max_pages,
                    content_key=json_path,
                    last_key="last",
                    total_pages_key="totalPages",
                ):
                    if not isinstance(page_content, list):
                        page_content = [page_content]

                    for item in page_content:
                        total_items_checked += 1
                        match = _find_match(item, needle)
                        if match is not None:
                            result["found"] = True
                            result["matched_content"] = match
                            break

                    if result["found"]:
                        break

                if total_items_checked == 0:
                    result["error"] = f"No data found at JSON path '{json_path}'"

                logger.debug(
                    "API check: searched %d items at path '%s' in %s, found=%s",
                    total_items_checked,
                    json_path,
                    url,
                    result["found"],
                )

            except requests.RequestException as exc:
                result["error"] = f"Request failed: {exc}"
                logger.debug("API request failed for %s: %s", url, exc)

            return result

        except Exception as exc:
            result["error"] = f"API check failed: {exc}"
            logger.debug("API check failed for %s: %s", url, exc)
            return result

    @staticmethod
    def dispatch_monitor(monitor: Monitor) -> dict:
        if monitor.type == "html_static":
            return MonitorService.check_html_static(
                url=monitor.url,
                selector=monitor.selector or "",
                target=monitor.target,
                case_sensitive=monitor.case_sensitive,
                timeout=monitor.timeout,
            )
        elif monitor.type == "html_javascript":
            return MonitorService.check_html_javascript(
                url=monitor.url,
                selector=monitor.selector or "",
                target=monitor.target,
                case_sensitive=monitor.case_sensitive,
                timeout=monitor.timeout,
                wait_selector=monitor.wait_selector,
            )
        elif monitor.type == "api":
            return MonitorService.check_api(
                url=monitor.url,
                json_path=monitor.json_path or "content",
                target=monitor.target,
                case_sensitive=monitor.case_sensitive,
                timeout=monitor.timeout,
                page_size=monitor.page_size or 32,
                max_pages=monitor.max_pages,
                request_delay=(monitor.request_delay or 0) / 1000.0,
            )
        else:
            return {
                "found": False,
                "matched_content": None,
                "error": f"Unknown monitor type: {monitor.type}",
            }

    @staticmethod
    async def run_monitor(session: AsyncSession, monitor: Monitor) -> Execution:
        raw = await run_in_threadpool(MonitorService.dispatch_monitor, monitor)
        status, result, error = _derive_status(raw)
        execution = await create_execution(
            session=session,
            monitor=monitor,
            status=status,
            result=result,
            error=error,
        )
        if status == "found":
            await upsert_alert(session=session, execution=execution)
        return execution

    @staticmethod
    async def run_due(session: AsyncSession) -> list[Execution]:
        monitors = await get_active_monitors(session=session)
        executions = []
        for monitor in monitors:
            executions.append(await MonitorService.run_monitor(session=session, monitor=monitor))
        return executions

    @staticmethod
    async def run_monitor_by_id(session: AsyncSession, monitor_id: int) -> Execution | None:
        monitor = await get_monitor(session=session, monitor_id=monitor_id)
        if monitor is None:
            return None
        return await MonitorService.run_monitor(session=session, monitor=monitor)
