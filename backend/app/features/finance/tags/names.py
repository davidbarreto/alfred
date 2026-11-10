def merge_tag_names(*groups: list[str]) -> list[str]:
    """Tag names from every group in order, without case-insensitive duplicates (first spelling wins)."""
    merged: list[str] = []
    seen: set[str] = set()
    for name in (name for group in groups for name in group):
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(name.strip())
    return merged
