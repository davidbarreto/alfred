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
    )


def _make_service(**kwargs):
    session = kwargs.get("session") or AsyncMock()
    session_service = kwargs.get("session_service") or AsyncMock()
    session_service.record_shadowing.return_value = MagicMock(id=1)
    chunk_repo = kwargs.get("chunk_repo") or AsyncMock()
    track_repo = kwargs.get("track_repo") or AsyncMock()
    audio_storage = kwargs.get("audio_storage") or AsyncMock()
    audio_converter = kwargs.get("audio_converter") or AsyncMock()
    audio_converter.to_ogg_opus.return_value = kwargs.get("ogg_audio", b"ogg-bytes")
    analysis_provider = kwargs.get("analysis_provider") or AsyncMock()
    analysis_provider.provider = "google"
    analysis_provider.model = "gemini-2.5-flash"

    service = ShadowingService(
        session=session, session_service=session_service, chunk_repo=chunk_repo, track_repo=track_repo,
        audio_storage=audio_storage, audio_converter=audio_converter, analysis_provider=analysis_provider,
    )
    return service, session, session_service, chunk_repo, track_repo, audio_storage, audio_converter, analysis_provider


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

    @pytest.mark.asyncio
    async def test_with_chunk_runs_analysis_and_derives_quality_score(self):
        service, session, session_service, chunk_repo, track_repo, audio_storage, audio_converter, analysis_provider = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk()
        track_repo.get_track.return_value = _make_track()
        analysis_provider.analyze_pronunciation.return_value = _make_analysis_result(score=85.0)

        with patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service.record_shadowing_with_audio(track_id=1, chunk_id=42, audio=b"raw-audio")

        audio_converter.to_ogg_opus.assert_awaited_once_with(b"raw-audio")
        audio_storage.save.assert_awaited_once()
        saved_bytes, saved_ref = audio_storage.save.call_args.args
        assert saved_bytes == b"ogg-bytes"
        assert saved_ref.startswith("shadowing/") and saved_ref.endswith(".ogg")

        analysis_provider.analyze_pronunciation.assert_awaited_once_with(
            b"ogg-bytes", "audio/ogg", "bonjour", "hello", "French",
        )

        create_call = session_service.record_shadowing.call_args
        data = create_call.args[0]
        assert data.quality_score == score_to_quality(85.0)
        assert data.ai_feedback_json["transcription"] == "bonjour"
        assert data.transcript_or_notes == "Clear and natural."
        assert create_call.kwargs["audio_ref"] == saved_ref

        mock_log.assert_awaited_once()
        log_call = mock_log.call_args
        assert log_call.args[0] is session
        assert log_call.kwargs["provider"] == "google"
        assert log_call.kwargs["model"] == "gemini-2.5-flash"
        assert log_call.kwargs["feature"] == "pronunciation_analysis"
        assert log_call.kwargs["response"] == '{"score": 85}'
        assert log_call.kwargs["tokens_input"] == 100
        assert log_call.kwargs["tokens_output"] == 50
        assert log_call.kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_without_chunk_id_skips_analysis(self):
        service, session, session_service, chunk_repo, track_repo, audio_storage, audio_converter, analysis_provider = _make_service()

        with patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service.record_shadowing_with_audio(track_id=1, chunk_id=None, audio=b"raw-audio")

        chunk_repo.get_chunk.assert_not_awaited()
        analysis_provider.analyze_pronunciation.assert_not_awaited()
        mock_log.assert_not_awaited()
        data = session_service.record_shadowing.call_args.args[0]
        assert data.quality_score is None
        assert data.ai_feedback_json is None
        audio_storage.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_chunk_skips_analysis(self):
        service, session, session_service, chunk_repo, track_repo, audio_storage, audio_converter, analysis_provider = _make_service()
        chunk_repo.get_chunk.return_value = None

        with patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service.record_shadowing_with_audio(track_id=1, chunk_id=42, audio=b"raw-audio")

        analysis_provider.analyze_pronunciation.assert_not_awaited()
        mock_log.assert_not_awaited()
        data = session_service.record_shadowing.call_args.args[0]
        assert data.quality_score is None

    @pytest.mark.asyncio
    async def test_analysis_failure_still_saves_audio_and_session(self):
        service, session, session_service, chunk_repo, track_repo, audio_storage, audio_converter, analysis_provider = _make_service()
        chunk_repo.get_chunk.return_value = _make_chunk()
        track_repo.get_track.return_value = _make_track()
        analysis_provider.analyze_pronunciation.side_effect = RuntimeError("gemini boom")

        with patch("app.features.language.sessions.shadowing_service.create_llm_call", AsyncMock()) as mock_log:
            await service.record_shadowing_with_audio(track_id=1, chunk_id=42, audio=b"raw-audio")

        audio_storage.save.assert_awaited_once()
        mock_log.assert_not_awaited()
        data = session_service.record_shadowing.call_args.args[0]
        assert data.quality_score is None
        assert data.ai_feedback_json is None
        assert session_service.record_shadowing.call_args.kwargs["audio_ref"] is not None
