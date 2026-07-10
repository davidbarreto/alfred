SENTENCE_TASK_TEMPLATE = (
    'Write an original sentence in {language_name} using "{text}" ({translation}).'
)

TRANSLATE_TASK_TEMPLATE = (
    'Translate into {language_name}: "{source_text}"'
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
