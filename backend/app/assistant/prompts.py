INTENT_EXTRACTION_PROMPT_TEMPLATE = (
    "Extract the requested structured fields from the user message. "
    "{date_context}"
    "Return ONLY a valid JSON object matching this schema — no explanation or commentary:\n{schema}"
)

DATE_CONTEXT_TEMPLATE = (
    "The current date and time is {now}. "
    "Use it to resolve relative date expressions like 'next Sunday' or 'tomorrow'. "
)
