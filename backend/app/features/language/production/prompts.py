SENTENCE_TASK_TEMPLATE = (
    'Write an original sentence in {language_name} using "{text}" ({translation}).'
)

TRANSLATE_TASK_TEMPLATE = (
    'Translate into {language_name}: "{source_text}"'
)

JOURNAL_TASK_TEMPLATE = (
    "Write a short journal entry in {language_name} (3-5 sentences) about {topic}.{suggestion_line}"
)

TIMED_TASK_TEMPLATE = (
    "Timed writing ({minutes} min): write as much as you can in {language_name} about {topic}. "
    "Keep writing — don't stop to fix mistakes.{suggestion_line}"
)

SUGGESTION_LINE_TEMPLATE = " Try to use: {chunk_list}."

JOURNAL_TOPICS: tuple[str, ...] = (
    "your day so far",
    "something you're looking forward to",
    "the last meal you really enjoyed",
    "a person you talked to recently",
    "your plans for tomorrow",
    "something that annoyed you recently",
    "a place you visited recently",
)

TIMED_TOPICS: tuple[str, ...] = (
    "your typical morning",
    "your hometown",
    "your favorite meal",
    "the last trip you took",
    "your work or studies",
    "a hobby you enjoy",
    "the weather and the seasons",
)

PRODUCTION_GRADING_PROMPT = """You are grading a {language_name} production exercise (CEFR level {cefr_level}).
Task type: {task_type}
Target chunk: "{text}" (translation: "{translation}")
Task given to the student: {prompt_text}
{reference_line}
Student's answer: {response_text}

Grade the answer for correctness and naturalness. For "sentence" tasks the sentence must
actually use the target chunk. For "translate" tasks meaning-preserving variation is fine.
Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "score": 85,
  "errors": ["..."],
  "corrected_text": "...",
  "feedback": "...",
  "new_vocabulary": [{{"text": "...", "translation": "..."}}]
}}
"score" is 0-100. "errors" lists concrete mistakes (empty if none). "corrected_text" is the
answer rewritten naturally (or the answer unchanged if already correct). "feedback" is one or
two short encouraging sentences. "new_vocabulary" holds up to 3 useful {language_name} words or
expressions the student struggled with or should learn next (empty if none)."""

OPEN_ENDED_GRADING_PROMPT = """You are grading a {language_name} free-writing exercise (CEFR level {cefr_level}).
Task type: {task_type}
Task given to the student: {prompt_text}
Student's text: {response_text}

Grade the text holistically for correctness, naturalness, and range at this CEFR level.
For "journal" tasks value personal, connected sentences. For "timed" tasks reward fluency and
quantity; be lenient on typos and minor slips made under time pressure.
Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "score": 85,
  "errors": ["..."],
  "corrected_text": "...",
  "feedback": "...",
  "new_vocabulary": [{{"text": "...", "translation": "..."}}]
}}
"score" is 0-100. "errors" lists concrete mistakes (empty if none). "corrected_text" is the
full text rewritten naturally (or unchanged if already correct). "feedback" is one or two short
encouraging sentences. "new_vocabulary" holds up to 5 useful {language_name} words or expressions
the student struggled with, worked around, or should learn next (empty if none)."""
