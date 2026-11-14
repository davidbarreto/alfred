def normalize_tag_name(name: str) -> str:
    """Tags are stored trimmed and lowercase, so "Family" and "family" are the same tag everywhere."""
    return name.strip().lower()
