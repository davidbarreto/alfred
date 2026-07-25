ROLEPLAY_OPENING_PROMPT = """\
You are about to roleplay a scenario with David to help him practice {language_name}.
Scenario: {scenario}

Write a short opening line, entirely in {language_name}, that sets the scene and stays in \
character to kick off the roleplay. 1-2 sentences. Return only the line, no explanation, no quotes."""

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

Reply naturally and in character, entirely in {language_name}. Keep replies short, like real speech.
If David's turn has a clear pronunciation or grammar issue worth flagging, note it briefly in "tip" — \
not every turn, only when there's something genuinely useful to point out. Otherwise leave "tip" null.
Keep the correction out of your reply itself — stay in character there.

""" + _TURN_JSON_CONTRACT

CONVERSATION_TURN_PROMPT = """\
You are having a free-flowing conversation with David in {language_name}, purely for \
conversation practice. {topic_line}

Reply naturally and conversationally, entirely in {language_name}. Keep replies short, like real speech.
This is casual practice, not a graded exercise — do not lecture or over-correct.
If David's turn has a clear pronunciation or grammar issue worth flagging, note it briefly in "tip" — \
not every turn, only when there's something genuinely useful to point out. Otherwise leave "tip" null.
Keep the correction out of your reply itself — it should read as natural conversation.

""" + _TURN_JSON_CONTRACT

ROLEPLAY_SUMMARY_PROMPT = """\
This roleplay conversation practice in {language_name} has ended. Scenario: {scenario}

Write a short, encouraging wrap-up (3-5 sentences) for David: how the roleplay went, and 1-3 concrete, \
specific things to work on next time, drawing on the notes below where relevant. Base your feedback on \
what David actually said — quote or reference his own words where it helps. Plain text, no markdown.

Transcript:
{transcript}

Notes captured during the conversation:
{tips}"""

CONVERSATION_SUMMARY_PROMPT = """\
This free conversation practice session in {language_name} has ended. {topic_line}

Write a short, encouraging wrap-up (3-5 sentences) for David: how the conversation went, and 1-3 concrete, \
specific things to work on next time, drawing on the notes below where relevant. Base your feedback on \
what David actually said — quote or reference his own words where it helps. Plain text, no markdown.

Transcript:
{transcript}

Notes captured during the conversation:
{tips}"""
