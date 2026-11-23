"""Text handed to a style-steerable TTS provider."""


def styled_for_tts(
    text: str, tone: str | None, language_name: str | None = None, slow: bool = False
) -> str:
    """Prefix text with a natural-language delivery instruction a style-steerable TTS
    provider can act on (it speaks only `text`, not the instruction itself).

    Always wraps, even without a tone: bare text handed straight to Gemini's native TTS
    can get misread as a chat prompt rather than a script to read verbatim — e.g. an A0
    conversation opening like `Try saying: "Bonjour" (Hello)` made the model try to
    answer it in text instead of voicing it, which the API rejects outright since that
    endpoint only ever returns audio.

    Also pins the voice/pitch and flags English/target-language mixing explicitly: left
    to its own devices, the model has been observed drifting to a noticeably different
    pitch per tone word (occasionally reading as a different speaker entirely), and
    outright dropping English asides — e.g. parenthetical translations in A0 replies —
    instead of voicing them, which left bilingual replies audibly missing the English
    half entirely rather than just mispronouncing it.

    `slow` asks for a beginner-friendly pace (used for CEFR A0, where the learner is
    hearing the target language for close to the first time)."""
    delivery = f"in a {tone} tone" if tone else "exactly as written"
    pace_note = " Speak slowly and clearly, at a pace a total beginner can follow." if slow else ""
    mix_note = (
        f" This text mixes English and {language_name} — read every single word of both "
        f"languages aloud, in order, pronouncing each natively; do not skip, omit, or "
        f"summarize any part of it, including anything in parentheses."
        if language_name
        else ""
    )
    return (
        f"Say {delivery}, in the same steady voice and pitch throughout — vary only energy "
        f"and pacing for the tone, never the pitch or voice itself. Read the entire text "
        f"below verbatim, word for word, omitting nothing.{pace_note}{mix_note} Text: {text}"
    )
