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

    def test_always_forbids_skipping_any_part_of_the_text(self):
        result = styled_for_tts("hello there", None)
        assert "Read the entire text below verbatim, word for word, omitting nothing" in result

    def test_language_name_forbids_omitting_parenthetical_asides(self):
        result = styled_for_tts("Привет (Hi)", "cheerful", language_name="Russian")
        assert "do not skip, omit, or summarize any part of it, including anything in parentheses" in result

    def test_slow_adds_a_beginner_pace_note(self):
        result = styled_for_tts("hello there", None, slow=True)
        assert "Speak slowly and clearly, at a pace a total beginner can follow." in result

    def test_not_slow_by_default(self):
        result = styled_for_tts("hello there", None)
        assert "Speak slowly" not in result
