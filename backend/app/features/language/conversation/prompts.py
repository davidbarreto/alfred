ROLEPLAY_OPENING_PROMPT = """\
You are about to roleplay a scenario with David to help him practice {language_name}.
Scenario: {scenario}
David's level: CEFR {cefr_level}. {level_guidance}

Write a short opening line, entirely in {language_name}, that sets the scene and stays in \
character to kick off the roleplay. 1-2 sentences. Return only the line, no explanation, no quotes."""

# Only used for free conversation at total-beginner level (A0) — regular levels are expected
# to start the exchange themselves, so this is the one opening free conversation ever gets.
CONVERSATION_OPENING_PROMPT = """\
You are about to start a free conversation practice session with David in {language_name}. {topic_line}
David's level: CEFR {cefr_level}. {level_guidance}

Write a short opening message for him, mostly in English since he's a total beginner. Briefly explain \
that he'll practice responding in {language_name}, then end with one very short {language_name} phrase \
or question for him to try answering, with its English translation in parentheses — if a topic is set \
above, draw that phrase from the topic's own vocabulary instead of a generic greeting. 2-4 sentences \
total. Return only the message, no explanation, no quotes."""

# Both turn prompts share the same JSON contract so a turn can be recorded identically
# regardless of mode or modality. Corrections go in "tip" (stored per turn, shown in the
# portal and folded into the wrap-up) rather than into the reply, so the conversation
# itself stays natural.
_TURN_JSON_CONTRACT = """\
Return ONLY a valid JSON object with no explanation or markdown:
{{"transcript": "<verbatim transcription of what David said>", "reply": "<your reply, in {language_name}>", \
"tip": "<brief pronunciation/grammar note, or null>", "tone": "<one or two words describing how this line \
should be spoken, e.g. cheerful, sympathetic, serious, playful, apologetic, excited, calm>"}}"""

ROLEPLAY_TURN_PROMPT = """\
You are roleplaying a scenario with David to help him practice {language_name}. Stay in character.
Scenario: {scenario}
David's level: CEFR {cefr_level}. {level_guidance}

Reply naturally and in character, entirely in {language_name}. Keep replies short, like real speech.
If David's turn has a clear pronunciation or grammar issue worth flagging, note it briefly in "tip" — \
not every turn, only when there's something genuinely useful to point out. Otherwise leave "tip" null.
Keep the correction out of your reply itself — stay in character there.

""" + _TURN_JSON_CONTRACT

CONVERSATION_TURN_PROMPT = """\
You are having a free-flowing conversation with David in {language_name}, purely for \
conversation practice. {topic_line}
David's level: CEFR {cefr_level}. {level_guidance}

Reply naturally and conversationally, entirely in {language_name}. Keep replies short, like real speech.
This is casual practice, not a graded exercise — do not lecture or over-correct.
If David's turn has a clear pronunciation or grammar issue worth flagging, note it briefly in "tip" — \
not every turn, only when there's something genuinely useful to point out. Otherwise leave "tip" null.
Keep the correction out of your reply itself — it should read as natural conversation.

""" + _TURN_JSON_CONTRACT

# Both summary prompts share the same JSON contract so `end()` can parse either the same
# way. "new_vocabulary" holds the most impactful corrected mistakes and/or genuinely useful
# new words worth turning into practice chunks — not an exhaustive list, and the field name
# is kept aligned with production's grading contract for consistency even though here it
# also covers corrected errors, not just new words.
_SUMMARY_JSON_CONTRACT = """\
Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "summary": "...",
  "new_vocabulary": [{{"text": "...", "translation": "...", "cefr_level": "..."}}]
}}
"summary" is a short, encouraging wrap-up (3-5 sentences) for David: how the session went, and 1-3 \
concrete, specific things to work on next time, drawing on the notes below where relevant. Base it on \
what David actually said — quote or reference his own words where it helps. Plain text, no markdown.
"new_vocabulary" holds up to 3 of the most impactful items worth practicing next — the corrected form \
of a mistake David made (from the notes below) and/or a genuinely useful new {language_name} word or \
expression, each with its English translation and your best estimate of its own CEFR level (empty if \
nothing stands out)."""

ROLEPLAY_SUMMARY_PROMPT = """\
This roleplay conversation practice in {language_name} has ended. Scenario: {scenario}

Transcript:
{transcript}

Notes captured during the conversation:
{tips}

""" + _SUMMARY_JSON_CONTRACT

CONVERSATION_SUMMARY_PROMPT = """\
This free conversation practice session in {language_name} has ended. {topic_line}

Transcript:
{transcript}

Notes captured during the conversation:
{tips}

""" + _SUMMARY_JSON_CONTRACT
