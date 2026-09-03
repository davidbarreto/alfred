JD_EXTRACTION_PROMPT_TEMPLATE = (
    "Extract structured job-posting fields from the page text below. "
    "For office_days_per_month, convert any phrasing about in-office attendance (e.g. '3 days a week', "
    "'1 week per quarter', 'fully remote', 'onsite') into a single number of days per month "
    "(0 for fully remote; ~4.3 * days_per_week for a weekly cadence). "
    "If a field isn't mentioned, omit it (leave it null). "
    "Return ONLY a valid JSON object matching this schema — no explanation or commentary:\n{schema}\n\n"
    "Page text:\n{text}"
)
