import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.language.sessions.shadowing_service import ShadowingService
from app.features.language.srs import score_to_quality
from app.shared.audio import PronunciationAnalysis, PronunciationAnalysisResult


def _make_chunk(**kwargs):
    chunk = MagicMock()
    chunk.track_id = kwargs.get("track_id", 1)
    chunk.text = kwargs.get("text", "bonjour")
    chunk.translation = kwargs.get("translation", "hello")
    return chunk


def _make_track(**kwargs):
    track = MagicMock()
    track.name = kwargs.get("name", "French")
    return track


def _make_analysis(**kwargs) -> PronunciationAnalysis:
    return PronunciationAnalysis(
        transcription=kwargs.get("transcription", "bonjour"),
        score=kwargs.get("score", 85.0),
        summary=kwargs.get("summary", "Clear and natural."),
        strengths=kwargs.get("strengths", ["Good vowels"]),
        issues=kwargs.get("issues", []),
        tip=kwargs.get("tip", "Stress the second syllable."),
    )


def _make_analysis_result(**kwargs) -> PronunciationAnalysisResult:
    return PronunciationAnalysisResult(
        analysis=kwargs.get("analysis") or _make_analysis(score=kwargs.get("score", 85.0)),
        raw_response=kwargs.get("raw_response", '{"score": 85}'),
        tokens_input=kwargs.get("tokens_input", 100),
        tokens_output=kwargs.get("tokens_output", 50),
        finish_reason=kwargs.get("finish_reason", "STOP"),
    )


def _make_service(**kwargs):
    session = kwargs.get("session") or AsyncMock()
    session_service = kwargs.get("session_service") or AsyncMock()
    session_service.record_shadowing.return_value = MagicMock(id=1)
    audio_storage = kwargs.get("audio_storage") or AsyncMock()
    audio_converter = kwargs.get("audio_converter") or AsyncMock()
    audio_converter.to_ogg_opus.return_value = kwargs.get("ogg_audio", b"ogg-bytes")
    analysis_provider = kwargs.get("analysis_provider") or AsyncMock()
    analysis_provider.provider = "google"
    analysis_provider.model = "gemini-2.5-flash"

    service = ShadowingService(
        session=session, session_service=session_service,
        audio_storage=audio_storage, audio_converter=audio_converter, analysis_provider=analysis_provider,
    )
    return service, session, session_service, audio_storage, audio_converter, analysis_provider


class TestScoreToQuality:

    def test_zero_maps_to_again(self):
        assert score_to_quality(0) == 1.0

    def test_fifty_maps_to_hard_good_boundary(self):
        assert score_to_quality(50) == 2.5

    def test_hundred_maps_to_easy(self):
        assert score_to_quality(100) == 4.0

    def test_clamps_out_of_range_values(self):
        assert score_to_quality(-10) == 1.0
        assert score_to_quality(150) == 4.0


class TestRecordShadowingWithAudio:
    """Fast path: save audio, create a pending/skipped session, and hand grading off to the
    background — no LLM call happens inline."""

    @pytest.mark.asyncio
    async def test_with_chunk_saves_audio_and_schedules_grading(self):
        service, session, session_service, audio_storage, audio_converter, analysis_provider = _make_service()
        background_tasks = MagicMock()

        result = await service.record_shadowing_with_audio(
            track_id=1, chunk_id=42, audio=b"raw-audio", background_tasks=background_tasks,
        )

        audio_converter.to_ogg_opus.assert_awaited_once_with(b"raw-audio")
        audio_storage.save.assert_awaited_once()
        saved_bytes, saved_ref = audio_storage.save.call_args.args
        assert saved_bytes == b"ogg-bytes"
        assert saved_ref.startswith("shadowing/") and saved_ref.endswith(".ogg")

        create_call = session_service.record_shadowing.call_args
        data = create_call.args[0]
        assert data.track_id == 1
        assert data.chunk_id == 42
        assert data.quality_score is None
        assert data.ai_feedback_json is None
        assert create_call.kwargs["audio_ref"] == saved_ref
        assert create_call.kwargs["grading_status"] == "pending"

        analysis_provider.analyze_pronunciation.assert_not_awaited()
        background_tasks.add_task.assert_called_once_with(
            service._grade_shadowing_in_background, result.id, 42, 1, b"ogg-bytes",
        )

    @pytest.mark.asyncio
    async def test_without_chunk_id_skips_grading(self):
        service, session, session_service, audio_storage, audio_converter, analysis_provider = _make_service()
        background_tasks = MagicMock()

        await service.record_shadowing_with_audio(
            track_id=1, chunk_id=None, audio=b"raw-audio", background_tasks=background_tasks,
        )

        create_call = session_service.record_shadowing.call_args
        assert create_call.kwargs["grading_status"] == "skipped"
        background_tasks.add_task.assert_not_called()
        audio_storage.save.assert_awaited_once()


class TestGradeShadowingInBackground:
    """The deferred grading step: opens its own DB session and updates the pending row."""

    @pytest.mark.asyncio
    async def test_success_updates_session_as_done(self):
        service, _, _, _, _, analysis_provider = _make_service()
        chunk_repo = AsyncMock()
        chunk_repo.get_chunk.return_value = _make_chunk()
        track_repo = AsyncMock()
        track_repo.get_track.return_value = _make_track()
        session_service = AsyncMock()
        analysis_provider.analyze_pronunciation.return_value = _make_analysis_result(score=85.0)

        db_session = AsyncMock()
        async_session_cm = AsyncMock()
        async_session_cm.__aenter__.return_value = db_session

        with patch("app.features.language.sessions.shadowing_service.async_session", return_value=async_session_cm), \
             patch("app.features.language.sessions.shadowing_service.ChunkRepository", return_value=chunk_repo), \
             patch("app.features.language.sessions.shadowing_service.TrackRepository", return_value=track_repo), \
             patch("app.features.language.sessions.shadowing_service.SessionService", return_value=session_service), \
             patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service._grade_shadowing_in_background(
                session_id=7, chunk_id=42, track_id=1, ogg_audio=b"ogg-bytes",
            )

        analysis_provider.analyze_pronunciation.assert_awaited_once_with(
            b"ogg-bytes", "audio/ogg", "bonjour", "hello", "French",
        )
        mock_log.assert_awaited_once()
        assert mock_log.call_args.args[0] is db_session

        session_service.update_shadowing_grading.assert_awaited_once()
        call = session_service.update_shadowing_grading.call_args
        assert call.args[0] == 7
        assert call.kwargs["quality_score"] == score_to_quality(85.0)
        assert call.kwargs["ai_feedback_json"]["transcription"] == "bonjour"
        assert call.kwargs["transcript_or_notes"] == "Clear and natural."
        assert call.kwargs["grading_status"] == "done"

    @pytest.mark.asyncio
    async def test_analysis_failure_marks_grading_failed(self):
        service, _, _, _, _, analysis_provider = _make_service()
        chunk_repo = AsyncMock()
        chunk_repo.get_chunk.return_value = _make_chunk()
        track_repo = AsyncMock()
        track_repo.get_track.return_value = _make_track()
        session_service = AsyncMock()
        analysis_provider.analyze_pronunciation.side_effect = RuntimeError("gemini boom")

        async_session_cm = AsyncMock()
        async_session_cm.__aenter__.return_value = AsyncMock()

        with patch("app.features.language.sessions.shadowing_service.async_session", return_value=async_session_cm), \
             patch("app.features.language.sessions.shadowing_service.ChunkRepository", return_value=chunk_repo), \
             patch("app.features.language.sessions.shadowing_service.TrackRepository", return_value=track_repo), \
             patch("app.features.language.sessions.shadowing_service.SessionService", return_value=session_service), \
             patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service._grade_shadowing_in_background(
                session_id=7, chunk_id=42, track_id=1, ogg_audio=b"ogg-bytes",
            )

        mock_log.assert_not_awaited()
        session_service.update_shadowing_grading.assert_awaited_once_with(7, None, None, None, "failed")

    @pytest.mark.asyncio
    async def test_missing_chunk_marks_grading_failed(self):
        service, _, _, _, _, analysis_provider = _make_service()
        chunk_repo = AsyncMock()
        chunk_repo.get_chunk.return_value = None
        track_repo = AsyncMock()
        session_service = AsyncMock()

        async_session_cm = AsyncMock()
        async_session_cm.__aenter__.return_value = AsyncMock()

        with patch("app.features.language.sessions.shadowing_service.async_session", return_value=async_session_cm), \
             patch("app.features.language.sessions.shadowing_service.ChunkRepository", return_value=chunk_repo), \
             patch("app.features.language.sessions.shadowing_service.TrackRepository", return_value=track_repo), \
             patch("app.features.language.sessions.shadowing_service.SessionService", return_value=session_service):
            await service._grade_shadowing_in_background(
                session_id=7, chunk_id=42, track_id=1, ogg_audio=b"ogg-bytes",
            )

        analysis_provider.analyze_pronunciation.assert_not_awaited()
        session_service.update_shadowing_grading.assert_awaited_once_with(7, None, None, None, "failed")
