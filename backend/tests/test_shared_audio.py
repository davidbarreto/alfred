from app.shared.audio import styled_for_tts


class TestStyledForTts:
    def test_no_tone_still_wraps_with_a_read_verbatim_instruction(self):
        result = styled_for_tts("hello there", None)
        assert result.startswith("Say exactly as written, in the same steady voice and pitch")
        assert result.endswith("Text: hello there")

    def test_empty_tone_still_wraps_with_a_read_verbatim_instruction(self):
        result = styled_for_tts("hello there", "")
        assert result.startswith("Say exactly as written, in the same steady voice and pitch")
        assert result.endswith("Text: hello there")

    def test_tone_prefixes_a_delivery_instruction(self):
        result = styled_for_tts("hello there", "cheerful")
        assert result.startswith("Say in a cheerful tone, in the same steady voice and pitch")
        assert result.endswith("Text: hello there")

    def test_pins_voice_and_pitch_regardless_of_tone(self):
        result = styled_for_tts("hello there", "excited")
        assert "never the pitch or voice itself" in result

    def test_no_language_name_omits_mix_note(self):
        result = styled_for_tts("hello there", None)
        assert "mixes English" not in result

    def test_language_name_adds_bilingual_pronunciation_note(self):
        result = styled_for_tts("Привет (Hi)", "cheerful", language_name="Russian")
        assert "This text mixes English and Russian" in result
        assert "Text: Привет (Hi)" in result
