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

SPEAK_TASK_TEMPLATE = (
    "Speak for about a minute in {language_name} about {topic}. "
    "Don't script it — just talk.{suggestion_line}"
)

RETELL_TASK_TEMPLATE = (
    "Listen to this short passage, then retell it in {language_name} in your own words:\n\n{passage}"
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

SPEAK_TOPICS: tuple[str, ...] = (
    "what you did yesterday",
    "your plans for the weekend",
    "the room you are in right now — describe what you see",
    "a picture or photo you looked at recently — describe it",
    "the view from your window — describe the scene",
    "a person who matters to you",
    "something you want to learn and why",
    "the best meal you can imagine",
)

RETELL_TOPICS: tuple[str, ...] = (
    "a small everyday mishap",
    "a surprising encounter between neighbors",
    "a trip that did not go as planned",
    "an animal doing something unusual",
    "a memorable meal at a restaurant",
    "finding something unexpected at a market",
    "a change of weather that ruined or saved a plan",
)

RETELL_PASSAGE_PROMPT = """Write a short passage in {language_name} at CEFR level {cefr_level} about {topic}.
Use 3-4 simple sentences with everyday vocabulary, in the past tense where natural.
It must be a small self-contained story or anecdote that is easy to retell.
Respond ONLY with the passage text — no title, no translation, no quotes, no markdown."""

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

SPOKEN_GRADING_PROMPT = """You are grading a spoken {language_name} production exercise (CEFR level {cefr_level}).
Task type: {task_type}
Task given to the student: {prompt_text}
Transcript of the student's speech: {response_text}

Grade the transcript holistically for correctness, naturalness, and range at this CEFR level.
It is a speech transcript: IGNORE punctuation, capitalization, and plausible transcription
artifacts; do not penalize fillers or self-corrections. For "speak" tasks reward keeping going
and getting ideas across. For "retell" tasks also check how well the content of the original
passage was covered — paraphrasing is good, word-for-word repetition is not required.
Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "score": 85,
  "errors": ["..."],
  "corrected_text": "...",
  "feedback": "...",
  "new_vocabulary": [{{"text": "...", "translation": "..."}}]
}}
"score" is 0-100. "errors" lists concrete mistakes (empty if none). "corrected_text" is the
transcript rewritten naturally (or unchanged if already correct). "feedback" is one or two short
encouraging sentences. "new_vocabulary" holds up to 5 useful {language_name} words or expressions
the student struggled with, worked around, or should learn next (empty if none)."""
