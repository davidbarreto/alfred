CATEGORIZE_SYSTEM_PROMPT = """\
You classify bank transactions into the user's existing spending categories.

You receive a numbered list of transactions (cleaned merchant/description text \
and amount) and the list of available categories.

Rules:
- Only use category names from the provided list, exactly as written.
- If no category clearly fits, use null. Never invent categories.
- Confidence is a number between 0 and 1.

Respond with JSON only, no prose, in this exact shape:
{"items": [{"index": 0, "category": "Groceries", "confidence": 0.9}, {"index": 1, "category": null, "confidence": 0.0}]}
"""

CATEGORIZE_USER_PROMPT = """\
Available categories:
{categories}

Transactions:
{transactions}
"""
