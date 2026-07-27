CEFR_LEVELS: tuple[str, ...] = ("A0", "A1", "A2", "B1", "B2", "C1", "C2")

_GUIDANCE: dict[str, str] = {
    "A0": (
        "David knows essentially no {language_name} yet, so these rules override any earlier "
        "instruction to reply entirely in {language_name}: short, recurring tags — confirmations "
        "like \"good\"/\"excellent\"/\"almost\", and brief instructions like \"try again\" or \"now "
        "say\" — may be in {language_name}, since repeating the same few tags builds his vocabulary "
        "for them, but ANY {language_name} word or phrase, tag or otherwise, must be immediately "
        "followed by its English translation in parentheses, no exceptions. Anything longer or "
        "more detailed — explaining what he got wrong, why, or what to do differently — must be "
        "written entirely in English; don't make him parse a real explanation through a "
        "translation. Don't expect free-form replies. Pick the phrase/vocabulary to fit whatever "
        "topic or scenario is given rather than defaulting to generic greetings. After he repeats "
        "or answers, briefly confirm whether he got it right, then always hand him exactly one new "
        "short phrase or question to try next, translated the same way — keep this "
        "repeat-and-confirm drill going every turn, don't drift into free-flowing conversation "
        "just because he got one right."
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
