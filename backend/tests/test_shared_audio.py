from app.shared.audio import styled_for_tts


class TestStyledForTts:
    def test_no_tone_returns_text_unchanged(self):
        assert styled_for_tts("hello there", None) == "hello there"

    def test_empty_tone_returns_text_unchanged(self):
        assert styled_for_tts("hello there", "") == "hello there"

    def test_tone_prefixes_a_delivery_instruction(self):
        result = styled_for_tts("hello there", "cheerful")
        assert result == "Say in a cheerful tone: hello there"
