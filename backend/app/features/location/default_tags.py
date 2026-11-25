def clean_tag_names(text: str | None) -> str | None:
    """Comma-separated default finance tags of a city or country, as typed: blank means none."""
    return text.strip() or None if text else None
