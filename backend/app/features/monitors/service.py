from starlette.concurrency import run_in_threadpool
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

import logging
import requests

from bs4 import BeautifulSoup
from app.features.monitors.repository import create_monitor_log, get_active_monitors, get_monitor
from app.features.monitors.tables import Monitor
from app.integrations.http.pagination import paginate
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)

class MonitorService:
    @staticmethod
    def check_html_static(
        url: str,
        selector: str,
        target: str,
        case_sensitive: bool = True,
        timeout: int = 10,
    ) -> dict:
        """
        Check for target text in HTML elements matched by a CSS selector (static HTML, no JavaScript).
        """
        result = {
            "url": url,
            "selector": selector,
            "target": target,
            "case_sensitive": case_sensitive,
            "found": False,
            "elements_checked": 0,
            "error": None,
            "timeout": timeout,
            "monitor_type": "html_static",
        }

        try:
            headers = {"User-Agent": "Mozilla/5.0 (alfred/1.0)"}
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            result["error"] = f"Request failed: {exc}"
            logger.debug("Request failed for %s: %s", url, exc)
            return result

        # Log a short snippet of the fetched HTML so you can inspect it server-side
        logger.debug("Fetched URL %s status=%s html_length=%d", url, getattr(response, "status_code", None), len(response.text or ""))
        snippet = (response.text or "")[:2000]
        logger.debug("HTML snippet (first 2000 chars) for %s:\n%s", url, snippet)

        soup = BeautifulSoup(response.text, "html.parser")
        elements = soup.select(selector)
        result["elements_checked"] = len(elements)

        logger.debug("Selector '%s' matched %d elements for %s", selector, len(elements), url)
        if elements:
            try:
                first_text = elements[0].get_text(separator=" ", strip=True)
                logger.debug("First matched element text: %s", first_text[:500])
            except Exception:
                logger.debug("Unable to get text of first matched element")

        if not elements:
            result["error"] = f"No elements matched selector '{selector}'"
            return result

        needle = target if case_sensitive else target.lower()
        for element in elements:
            text = element.get_text(separator=" ", strip=True)
            haystack = text if case_sensitive else text.lower()
            if needle in haystack:
                result["found"] = True
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
        """
        Check for target text in HTML elements matched by a CSS selector with JavaScript rendering.
        Uses Selenium with headless Chrome to render JavaScript content.
        """
        result = {
            "url": url,
            "selector": selector,
            "target": target,
            "case_sensitive": case_sensitive,
            "found": False,
            "elements_checked": 0,
            "error": None,
            "timeout": timeout,
            "monitor_type": "html_javascript",
        }

        try:
            # Configure headless Chrome
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument(f"--user-agent=Mozilla/5.0 (alfred/1.0)")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            try:
                driver.set_page_load_timeout(timeout)
                driver.get(url)

                # Wait for the target selector or wait_selector if provided
                selector_to_wait = wait_selector or selector
                if selector_to_wait:
                    try:
                        WebDriverWait(driver, timeout).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector_to_wait))
                        )
                        logger.debug("Waited for selector '%s' on %s", selector_to_wait, url)
                    except Exception as wait_exc:
                        logger.debug("Timeout waiting for selector '%s': %s", selector_to_wait, wait_exc)

                # Find elements
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                result["elements_checked"] = len(elements)

                logger.debug("Selector '%s' matched %d elements for %s (JS-rendered)", selector, len(elements), url)

                if not elements:
                    result["error"] = f"No elements matched selector '{selector}' after JS rendering"
                    return result

                # Check if target text is found
                needle = target if case_sensitive else target.lower()
                for element in elements:
                    try:
                        text = element.text
                        haystack = text if case_sensitive else text.lower()
                        if needle in haystack:
                            result["found"] = True
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
        """
        Check for target text in an API response by searching through paginated JSON data.
        Uses dot-notation paths to navigate nested JSON structures.
        
        Args:
            url: API endpoint
            json_path: Dot-notation path to search in (e.g., "content", "data.items", "meta.results")
            target: Text to find
            case_sensitive: Whether search is case-sensitive
            timeout: Request timeout in seconds
            page_size: Items per page
            max_pages: Maximum pages to fetch
            request_delay: Delay between requests in seconds
        """
        result = {
            "url": url,
            "json_path": json_path,
            "target": target,
            "case_sensitive": case_sensitive,
            "found": False,
            "elements_checked": 0,
            "error": None,
            "timeout": timeout,
            "monitor_type": "api",
        }

        def search_recursive(obj: Any, needle: str, case_sensitive: bool) -> bool:
            """Recursively search for needle in any value of a JSON structure."""
            if isinstance(obj, dict):
                return any(search_recursive(v, needle, case_sensitive) for v in obj.values())
            if isinstance(obj, list):
                return any(search_recursive(item, needle, case_sensitive) for item in obj)
            
            text = str(obj) if obj is not None else ""
            haystack = text if case_sensitive else text.lower()
            return needle in haystack

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
                    last_key="last",  # Default, can be customized if needed
                    total_pages_key="totalPages",
                ):
                    # page_content is a list of items from the JSON path
                    if not isinstance(page_content, list):
                        page_content = [page_content]

                    for item in page_content:
                        total_items_checked += 1
                        if search_recursive(item, needle, case_sensitive):
                            result["found"] = True
                            break
                            
                        if result["found"]:
                            break

                    if result["found"]:
                        break

                result["elements_checked"] = total_items_checked
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
        """
        Dispatch to the appropriate monitor check method based on monitor type.
        """
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
                request_delay=(monitor.request_delay or 0) / 1000.0,  # Convert ms to seconds
            )
        else:
            return {
                "error": f"Unknown monitor type: {monitor.type}",
                "found": False,
                "elements_checked": 0,
                "monitor_type": monitor.type,
                "url": monitor.url,
            }

    @staticmethod
    async def run_monitor(session: AsyncSession, monitor: Monitor):
        result = await run_in_threadpool(MonitorService.dispatch_monitor, monitor)
        return await create_monitor_log(session=session, monitor=monitor, result=result)

    @staticmethod
    async def run_due(session: AsyncSession):
        monitors = await get_active_monitors(session=session)
        logs = []
        for monitor in monitors:
            logs.append(await MonitorService.run_monitor(session=session, monitor=monitor))
        return logs

    @staticmethod
    async def run_monitor_by_id(session: AsyncSession, monitor_id: int):
        monitor = await get_monitor(session=session, monitor_id=monitor_id)
        if monitor is None:
            return None
        return await MonitorService.run_monitor(session=session, monitor=monitor)
