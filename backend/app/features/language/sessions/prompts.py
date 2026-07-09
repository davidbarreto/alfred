SHADOWING_ANALYSIS_PROMPT = """The student was shadowing: "{text}" in {language_name} (translation: {translation})

1. Transcribe exactly what they said.
2. Evaluate their pronunciation against the target.
Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "transcription": "...",
  "score": 85,
  "summary": "...",
  "strengths": ["..."],
  "issues": ["..."],
  "tip": "..."
}}"""
