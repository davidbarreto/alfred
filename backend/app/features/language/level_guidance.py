CEFR_LEVELS: tuple[str, ...] = ("A0", "A1", "A2", "B1", "B2", "C1", "C2")

_GUIDANCE: dict[str, str] = {
    "A0": (
        "David knows essentially no {language_name} yet. Keep it to very short, simple phrases "
        "he can repeat or recognize, translate key words in parentheses, and don't expect "
        "free-form replies. Pick the phrase/vocabulary to fit whatever topic or scenario is "
        "given rather than defaulting to generic greetings. After he repeats or answers, briefly "
        "confirm whether he got it right, then always hand him exactly one new short phrase or "
        "question to try next — keep this repeat-and-confirm drill going every turn, don't drift "
        "into free-flowing conversation just because he got one right."
    ),
    "A1": "Keep vocabulary and grammar very basic: short sentences, present tense, everyday words.",
    "A2": "Keep sentences short and grammar simple; everyday vocabulary, mostly present/past tense.",
    "B1": "Use natural everyday language; moderate sentence complexity is fine.",
    "B2": "Use natural, idiomatic language; more complex structures are fine.",
    "C1": "Use natural, nuanced language including idioms and varied structures.",
    "C2": "Use fully natural, native-level language without simplification.",
}


def level_guidance(level: str, language_name: str) -> str:
    """One instructional line for how simple/natural the LLM should keep its output at
    this CEFR level. Falls back to the A1 line for unrecognized values."""
    line = _GUIDANCE.get(level.upper(), _GUIDANCE["A1"])
    return line.format(language_name=language_name)
