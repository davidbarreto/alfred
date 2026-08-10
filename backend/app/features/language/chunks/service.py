import json
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.prompts import CHUNK_ENRICHMENT_PROMPT, CHUNK_TAG_SUGGESTION_PROMPT
from app.features.language.chunks.repository import ChunkRepository
from app.features.language.chunks.schemas import (
    ChunkCreate,
    ChunkFilters,
    ChunkRead,
    ChunkUpdate,
    DailyBatchRead,
    NewVocabularyCandidate,
    TagStatsRead,
)
from app.features.language.level_guidance import level_guidance
from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackFilters
from app.features.language.srs import (
    CardState,
    Rating,
    next_card_state,
    preview_next_intervals,
    quality_to_rating,
    is_leech,
)
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)

_MAX_FORCE_PRACTICE_TEXTS = 8
_MAX_TAG_SUGGESTION_BATCH = 30


def _recognition_card(orm) -> CardState:
    return CardState(
        stability=orm.stability,
        difficulty=orm.difficulty,
        due_at=orm.due_at,
        last_review_at=orm.last_review_at,
        repetitions=orm.repetitions,
        lapses=orm.lapses,
        consecutive_failures=orm.consecutive_failures,
        state=orm.state,
    )


def _chunk_read_with_preview(orm) -> ChunkRead:
    """Recognition ChunkRead with real FSRS-derived interval previews attached, for the
    review UI's Again/Hard/Good/Easy button labels."""
    read = ChunkRead.model_validate(orm)
    read.preview_intervals = preview_next_intervals(_recognition_card(orm))
    return read


def _parse_enrichment_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _production_card(orm) -> CardState:
    return CardState(
        stability=orm.prod_stability,
        difficulty=orm.prod_difficulty,
        due_at=orm.prod_due_at,
        last_review_at=orm.prod_last_review_at,
        repetitions=orm.prod_repetitions,
        lapses=orm.prod_lapses,
        consecutive_failures=orm.prod_consecutive_failures,
        state=orm.prod_state,
    )


class ChunkService:

    def __init__(self, session: AsyncSession, llm_provider: LlmProvider | None = None) -> None:
        self._session = session
        self._repo = ChunkRepository(session)
        self._track_repo = TrackRepository(session)
        self._llm_provider = llm_provider

    async def get_chunk(self, chunk_id: int) -> ChunkRead | None:
        orm = await self._repo.get_chunk(chunk_id)
        return ChunkRead.model_validate(orm) if orm else None

    async def get_chunks(self, filters: ChunkFilters) -> list[ChunkRead]:
        chunks = await self._repo.get_chunks(filters)
        return [ChunkRead.model_validate(c) for c in chunks]

    async def count_chunks(self, filters: ChunkFilters) -> int:
        return await self._repo.count_chunks(filters)

    async def create_chunk(self, data: ChunkCreate) -> ChunkRead:
        orm = await self._repo.create_chunk(data)
        logger.info("Chunk created: id=%d track_id=%d type=%r", orm.id, orm.track_id, orm.chunk_type)
        return ChunkRead.model_validate(orm)

    async def update_chunk(self, chunk_id: int, data: ChunkUpdate) -> ChunkRead | None:
        orm = await self._repo.update_chunk(chunk_id, data)
        if orm is None:
            return None
        logger.info("Chunk updated: id=%d", chunk_id)
        return ChunkRead.model_validate(orm)

    async def delete_chunk(self, chunk_id: int) -> None:
        await self._repo.delete_chunk(chunk_id)
        logger.info("Chunk deleted: id=%d", chunk_id)

    async def approve_chunk(self, chunk_id: int) -> ChunkRead | None:
        """Move a pending_triage chunk to active."""
        orm = await self._repo.get_chunk(chunk_id)
        if orm is None:
            return None
        update_data = ChunkUpdate(status="active")
        return await self.update_chunk(chunk_id, update_data)

    async def apply_srs_review(self, chunk_id: int, quality_score: float) -> ChunkRead | None:
        """Update recognition FSRS state for a chunk after a review session."""
        orm = await self._repo.get_chunk(chunk_id)
        if orm is None:
            return None

        rating = quality_to_rating(quality_score)
        now = datetime.now(timezone.utc)
        was_new = orm.state == "new"
        new_card = next_card_state(_recognition_card(orm), rating, now)
        leech = is_leech(new_card.consecutive_failures)

        await self._repo.update_srs_fields(
            chunk_id=chunk_id,
            stability=new_card.stability,
            difficulty=new_card.difficulty,
            due_at=new_card.due_at,
            last_review_at=new_card.last_review_at,
            repetitions=new_card.repetitions,
            lapses=new_card.lapses,
            consecutive_failures=new_card.consecutive_failures,
            state=new_card.state,
            is_leech=leech,
            first_reviewed_at=now if was_new else None,
        )

        if leech and not orm.is_leech:
            logger.warning("Chunk flagged as leech: id=%d consecutive_failures=%d", chunk_id, new_card.consecutive_failures)

        if rating >= Rating.GOOD and orm.prod_due_at is None:
            await self._repo.unlock_production(chunk_id, now)
            logger.info("Chunk unlocked for production practice: id=%d", chunk_id)

        updated = await self._repo.get_chunk(chunk_id)
        return ChunkRead.model_validate(updated)

    async def apply_production_review(self, chunk_id: int, quality_score: float) -> ChunkRead | None:
        """Update production FSRS state for a chunk after a production attempt."""
        orm = await self._repo.get_chunk(chunk_id)
        if orm is None:
            return None
        if orm.prod_due_at is None:
            logger.warning("Production review on locked chunk: id=%d — unlocking implicitly", chunk_id)

        rating = quality_to_rating(quality_score)
        now = datetime.now(timezone.utc)
        new_card = next_card_state(_production_card(orm), rating, now)

        await self._repo.update_production_srs_fields(
            chunk_id=chunk_id,
            stability=new_card.stability,
            difficulty=new_card.difficulty,
            due_at=new_card.due_at,
            last_review_at=new_card.last_review_at,
            repetitions=new_card.repetitions,
            lapses=new_card.lapses,
            consecutive_failures=new_card.consecutive_failures,
            state=new_card.state,
        )

        if is_leech(new_card.consecutive_failures):
            logger.warning(
                "Chunk struggling in production: id=%d prod_consecutive_failures=%d",
                chunk_id, new_card.consecutive_failures,
            )

        updated = await self._repo.get_chunk(chunk_id)
        return ChunkRead.model_validate(updated)

    async def suggest_tags_for_untagged(
        self, track_id: int, limit: int = _MAX_TAG_SUGGESTION_BATCH
    ) -> list[ChunkRead]:
        """LLM-assisted bulk tagging for the existing untagged backlog. Applies suggestions
        directly rather than through a separate preview/commit step — tags are a one-field
        edit to correct if a suggestion misses, the same risk level as approve_chunk triage."""
        if self._llm_provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI tag suggestion is not available",
            )

        track = await self._track_repo.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        chunks = await self._repo.get_chunks(ChunkFilters(
            track_id=track_id,
            status="active",
            untagged_only=True,
            limit=min(limit, _MAX_TAG_SUGGESTION_BATCH),
        ))
        if not chunks:
            return []

        existing_tags = await self._repo.get_tag_names_for_track(track_id)
        chunks_block = "\n".join(
            f'- id={c.id}: "{c.text}" ({c.translation}), {c.chunk_type}, {c.cefr_level or "?"}'
            for c in chunks
        )
        prompt = CHUNK_TAG_SUGGESTION_PROMPT.format(
            language_name=track.name,
            existing_tags=", ".join(existing_tags) if existing_tags else "(none yet)",
            chunks_block=chunks_block,
        )
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Chunk tag suggestion LLM call failed: track_id=%d error=%s", track_id, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not suggest tags. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="chunk_tag_suggestion",
            prompt=messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        try:
            suggestions = _parse_enrichment_json(llm_response.text)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("Chunk tag suggestion returned invalid JSON: track_id=%d error=%s", track_id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI tag suggestion returned an unreadable result. Please try again.",
            ) from exc

        updated: list[ChunkRead] = []
        for chunk in chunks:
            tag_names = suggestions.get(str(chunk.id))
            if not tag_names:
                continue
            result = await self.update_chunk(chunk.id, ChunkUpdate(tags=tag_names))
            if result is not None:
                updated.append(result)
        logger.info(
            "Chunk tags suggested via LLM: track_id=%d candidates=%d applied=%d",
            track_id, len(chunks), len(updated),
        )
        return updated

    async def get_tag_names(self, track_id: int) -> list[str]:
        return await self._repo.get_tag_names_for_track(track_id)

    async def get_tag_stats(self, track_id: int) -> list[TagStatsRead]:
        stats = await self._repo.get_tag_stats_for_track(track_id)
        return [TagStatsRead(**row) for row in stats]

    async def shift_due_dates(self, track_id: int, delta: timedelta) -> None:
        await self._repo.shift_due_dates(track_id, delta)
        logger.info("Chunk due dates shifted: track_id=%d delta_days=%.2f", track_id, delta.total_seconds() / 86400)

    async def get_daily_batch(
        self, track_id: int | None = None, states: list[str] | None = None
    ) -> list[DailyBatchRead]:
        """Return today's review batches per active track, Pareto-weighted.

        `track.active_tags` (persisted, multi-select "practice groups") narrows the batch
        when set; `states` is an ad hoc, non-persisted maturity filter passed in per-request
        (e.g. "only new" or "only review") that layers on top of it.
        """
        tracks_query = await self._track_repo.get_tracks(
            TrackFilters(active_only=True)
        )
        if track_id is not None:
            tracks_query = [t for t in tracks_query if t.id == track_id]

        batches = []
        for track in tracks_query:
            tag_names = track.active_tags or None
            total_due = await self._repo.count_due_for_track(track.id, tag_names, states)
            new_started_today = await self._repo.count_new_started_today_for_track(track.id)
            new_cards_limit = max(0, track.new_cards_per_day - new_started_today)
            chunks_orm = await self._repo.get_due_chunks_for_track(
                track.id, track.daily_quota, new_cards_limit, tag_names, states
            )
            batches.append(DailyBatchRead(
                track_id=track.id,
                track_code=track.code,
                chunks=[_chunk_read_with_preview(c) for c in chunks_orm],
                total_due=total_due,
            ))
        return batches

    async def force_practice_chunks(
        self, track_id: int, texts: list[str], level_override: str | None = None
    ) -> list[ChunkRead]:
        """Resolve or create chunks for the given texts so they can be practiced right away,
        regardless of SRS due date. Existing chunks are matched by exact (case-insensitive)
        text; new ones are LLM-enriched and created active/immediately due."""
        track = await self._track_repo.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

        seen: set[str] = set()
        deduped: list[str] = []
        for text in texts:
            cleaned = text.strip()
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                deduped.append(cleaned)
        deduped = deduped[:_MAX_FORCE_PRACTICE_TEXTS]
        if not deduped:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No words/phrases provided")

        results: list[ChunkRead] = []
        for text in deduped:
            orm = await self._repo.get_chunk_by_text(track_id, text)
            if orm is None:
                if self._llm_provider is None:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="AI enrichment is not available to create a new chunk",
                    )
                enrichment = await self._enrich_chunk_via_llm(track, text, level_override)
                orm = await self._repo.create_chunk(ChunkCreate(
                    track_id=track_id,
                    chunk_type=enrichment.get("chunk_type") or "word",
                    text=text,
                    translation=enrichment.get("translation") or "",
                    example_sentence=enrichment.get("example_sentence") or None,
                    example_translation=enrichment.get("example_translation") or None,
                    cefr_level=enrichment.get("cefr_level") or track.level,
                    frequency_source="user_requested",
                    status="active",
                ))
                logger.info(
                    "Chunk force-created for practice: id=%d track_id=%d text=%r",
                    orm.id, track_id, text,
                )
            results.append(_chunk_read_with_preview(orm))
        return results

    async def _enrich_chunk_via_llm(self, track, text: str, level_override: str | None) -> dict:
        prompt = CHUNK_ENRICHMENT_PROMPT.format(
            language_name=track.name,
            level_guidance=level_guidance(level_override or track.level, track.name),
            text=text,
        )
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        try:
            llm_response = await self._llm_provider.complete(messages)
        except Exception as exc:
            logger.error("Chunk enrichment LLM call failed: text=%r error=%s", text, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not look up that word/phrase. Please try again in a moment.",
            ) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        await create_llm_call(
            self._session,
            provider=self._llm_provider.provider,
            model=self._llm_provider.model,
            feature="chunk_enrichment",
            prompt=messages,
            response=llm_response.text,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            finish_reason=llm_response.finish_reason,
            latency_ms=latency_ms,
        )

        try:
            return _parse_enrichment_json(llm_response.text)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("Chunk enrichment returned invalid JSON: text=%r error=%s", text, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI enrichment returned an unreadable result. Please try again.",
            ) from exc

    async def queue_vocabulary_candidates(
        self,
        track_id: int,
        candidates: list[NewVocabularyCandidate],
        max_candidates: int,
    ) -> None:
        """Push LLM-suggested vocabulary/corrections into the existing triage/approval queue."""
        track = await self._track_repo.get_track(track_id)
        default_level = track.level if track else None
        for candidate in candidates[:max_candidates]:
            text = candidate.text.strip()
            if not text or not candidate.translation.strip():
                continue
            try:
                existing = await self._repo.get_chunk_by_text(track_id, text)
                if existing is not None:
                    logger.debug(
                        "Skipping duplicate vocabulary candidate: track_id=%d text=%r existing_id=%d status=%r",
                        track_id, text, existing.id, existing.status,
                    )
                    continue
                await self.create_chunk(ChunkCreate(
                    track_id=track_id,
                    chunk_type="word",
                    text=text,
                    translation=candidate.translation.strip(),
                    cefr_level=candidate.cefr_level or default_level,
                    frequency_source="llm_suggested",
                    status="pending_triage",
                ))
            except Exception:
                logger.error(
                    "Failed to queue vocabulary candidate: track_id=%d text=%r",
                    track_id, candidate.text, exc_info=True,
                )

    async def get_production_daily_batch(self, track_id: int | None = None) -> list[DailyBatchRead]:
        """Return today's production-due batches per active track, Pareto-weighted."""
        tracks_query = await self._track_repo.get_tracks(
            TrackFilters(active_only=True)
        )
        if track_id is not None:
            tracks_query = [t for t in tracks_query if t.id == track_id]

        batches = []
        for track in tracks_query:
            total_due = await self._repo.count_production_due_for_track(track.id)
            chunks_orm = await self._repo.get_production_due_chunks_for_track(track.id, track.daily_quota)
            batches.append(DailyBatchRead(
                track_id=track.id,
                track_code=track.code,
                chunks=[ChunkRead.model_validate(c) for c in chunks_orm],
                total_due=total_due,
            ))
        return batches
