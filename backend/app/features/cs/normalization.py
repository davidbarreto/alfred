"""Pure mapping functions from platform-specific raw values to Alfred's shared vocabulary.

Raw values are always kept alongside the normalized ones (on the ORM rows); these
functions never touch the DB or make network calls.
"""

_LANGUAGE_ALIASES: dict[str, str] = {
    "python": "python",
    "python3": "python",
    "python 3": "python",
    "python2": "python",
    "python 2": "python",
    "pypy": "python",
    "pypy3": "python",
    "pypy 3": "python",
    "c++": "cpp",
    "cpp": "cpp",
    "gnu c++": "cpp",
    "gnu c++11": "cpp",
    "gnu c++14": "cpp",
    "gnu c++17": "cpp",
    "gnu c++20": "cpp",
    "gnu c++17 (64 bit, ms c++)": "cpp",
    "gnu c++20 (64 bit, ms c++)": "cpp",
    "c": "c",
    "gnu c": "c",
    "gnu c11": "c",
    "java": "java",
    "java 8": "java",
    "java 11": "java",
    "java 17": "java",
    "java 21": "java",
    "javascript": "javascript",
    "nodejs": "javascript",
    "node.js": "javascript",
    "typescript": "typescript",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "rust 2021": "rust",
    "kotlin": "kotlin",
    "kotlin 1.6": "kotlin",
    "kotlin 1.7": "kotlin",
    "scala": "scala",
    "c#": "csharp",
    "c# 10": "csharp",
    "mono c#": "csharp",
    "ruby": "ruby",
    "swift": "swift",
    "php": "php",
}

_TAG_ALIASES: dict[str, str] = {
    "dp": "dynamic programming",
    "dynamic programming": "dynamic programming",
    "two pointers": "two pointers",
    "divide and conquer": "divide and conquer",
    "graphs": "graph",
    "graph": "graph",
    "trees": "tree",
    "tree": "tree",
    "greedy": "greedy",
    "binary search": "binary search",
    "sortings": "sorting",
    "sorting": "sorting",
    "data structures": "data structures",
    "strings": "string",
    "string": "string",
    "math": "math",
    "combinatorics": "combinatorics",
    "bitmask": "bitmask",
    "bit manipulation": "bitmask",
    "brute force": "brute force",
    "backtracking": "backtracking",
    "hash table": "hash table",
    "hashing": "hash table",
    "implementation": "implementation",
    "interactive": "interactive",
    "number theory": "number theory",
    "simulation": "simulation",
}

_VERDICT_ALIASES: dict[str, str] = {
    "ok": "accepted",
    "accepted": "accepted",
    "wrong_answer": "wrong_answer",
    "wrong answer": "wrong_answer",
    "time_limit_exceeded": "time_limit_exceeded",
    "time limit exceeded": "time_limit_exceeded",
    "memory_limit_exceeded": "memory_limit_exceeded",
    "memory limit exceeded": "memory_limit_exceeded",
    "runtime_error": "runtime_error",
    "runtime error": "runtime_error",
    "compilation_error": "compile_error",
    "compile error": "compile_error",
    "presentation_error": "other",
    "idleness_limit_exceeded": "other",
    "output limit exceeded": "other",
}

_CF_DIFFICULTY_BUCKETS: tuple[tuple[int, str], ...] = (
    (1200, "easy"),
    (1900, "medium"),
)


def normalize_language(raw: str | None) -> str | None:
    if not raw:
        return None
    return _LANGUAGE_ALIASES.get(raw.strip().lower())


def normalize_tag_name(raw: str) -> str:
    key = raw.strip().lower()
    return _TAG_ALIASES.get(key, key)


def normalize_verdict(raw: str) -> str:
    key = raw.strip().lower()
    return _VERDICT_ALIASES.get(key, "other")


def normalize_cf_difficulty(rating: int | None) -> str | None:
    if rating is None:
        return None
    for threshold, bucket in _CF_DIFFICULTY_BUCKETS:
        if rating < threshold:
            return bucket
    return "hard"


def normalize_leetcode_difficulty(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().lower()
