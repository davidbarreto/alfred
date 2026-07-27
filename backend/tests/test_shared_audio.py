from app.shared.audio import styled_for_tts


class TestStyledForTts:
    def test_no_tone_still_wraps_with_a_read_verbatim_instruction(self):
        assert styled_for_tts("hello there", None) == "Say exactly as written: hello there"

    def test_empty_tone_still_wraps_with_a_read_verbatim_instruction(self):
        assert styled_for_tts("hello there", "") == "Say exactly as written: hello there"

    def test_tone_prefixes_a_delivery_instruction(self):
        result = styled_for_tts("hello there", "cheerful")
        assert result == "Say in a cheerful tone: hello there"
