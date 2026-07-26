CHUNK_ENRICHMENT_PROMPT = """You are building a vocabulary entry for a {language_name} learner. \
{level_guidance}

Word or phrase: "{text}"

Respond ONLY with JSON (no markdown fences, even to format text as json):
{{
  "chunk_type": "word|collocation|verb_form|sentence_pattern",
  "translation": "...",
  "example_sentence": "...",
  "example_translation": "...",
  "cefr_level": "A1|A2|B1|B2|C1|C2"
}}
"chunk_type" should best classify the phrase. "translation" is the English meaning. \
"example_sentence" is a short, natural example in {language_name} using the phrase, with \
"example_translation" in English. "cefr_level" is your best estimate of the phrase's own \
intrinsic difficulty (A1-C2 only, regardless of how simply you were asked to explain it) — \
a word doesn't become easier just because the learner is a beginner."""
