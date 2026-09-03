from __future__ import annotations

import json
import logging
import time

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.features.organizer.interviews.processes.prompts import JD_EXTRACTION_PROMPT_TEMPLATE
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_MAX_PAGE_TEXT_CHARS = 8000
_FETCH_TIMEOUT_SECONDS = 10


class JobPostingExtraction(BaseModel):
    role_title: str | None = None
    company_name: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    work_regime: str | None = None
    office_days_per_month: float | None = None
    office_location: str | None = None
    benefits: str | None = None


def _fetch_page_text(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (alfred/1.0)"}
    response = requests.get(url, headers=headers, timeout=_FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.get_text(separator=" ", strip=True)[:_MAX_PAGE_TEXT_CHARS]


class JdExtractionService:
    def __init__(self, session: AsyncSession, llm_provider: LlmProvider) -> None:
        self._session = session
        self._llm_provider = llm_provider

    async def extract_from_url(self, url: str) -> JobPostingExtraction:
        page_text = await run_in_threadpool(_fetch_page_text, url)

        schema_str = json.dumps(JobPostingExtraction.model_json_schema(), indent=2)
        system_prompt = JD_EXTRACTION_PROMPT_TEMPLATE.format(schema=schema_str, text=page_text)
        messages = [{"role": "user", "content": "Extract the job posting fields."}]

        t0 = time.monotonic()
        llm_response = await self._llm_provider.complete(messages, system=system_prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="interview_jd_extraction",
            prompt=[{"role": "system", "content": system_prompt}] + messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        extraction = JobPostingExtraction.model_validate_json(raw)
        logger.debug("JD extraction successful: url=%s fields=%s", url, list(extraction.model_dump(exclude_none=True).keys()))
        return extraction
