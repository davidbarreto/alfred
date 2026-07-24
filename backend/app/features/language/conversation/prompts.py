ROLEPLAY_OPENING_PROMPT = """\
You are about to roleplay a scenario with David to help him practice {language_name}.
Scenario: {scenario}

Write a short opening line, entirely in {language_name}, that sets the scene and stays in \
character to kick off the roleplay. 1-2 sentences. Return only the line, no explanation, no quotes."""

ROLEPLAY_TURN_PROMPT = """\
You are roleplaying a scenario with David to help him practice {language_name}. Stay in character.
Scenario: {scenario}

Reply naturally and in character, entirely in {language_name}. Keep replies short, like real speech.
If David's turn has a clear pronunciation or grammar issue worth flagging, note it briefly in "tip" — \
not every turn, only when there's something genuinely useful to point out. Otherwise leave "tip" null.

Return ONLY a valid JSON object with no explanation or markdown:
{{"transcript": "<verbatim transcription of what David said>", "reply": "<your in-character reply, in {language_name}>", "tip": "<brief pronunciation/grammar note, or null>"}}"""

ROLEPLAY_SUMMARY_PROMPT = """\
This roleplay conversation practice in {language_name} has ended. Scenario: {scenario}

Write a short, encouraging wrap-up (3-5 sentences) for David: how the roleplay went, and 1-3 concrete, \
specific things to work on next time, drawing on the notes below where relevant. Plain text, no markdown.

Transcript:
{transcript}

Notes captured during the conversation:
{tips}"""
