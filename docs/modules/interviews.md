# Interview prep module

`organizer.interviews` helps track behavioral interview preparation with three main features, plus a shared tag vocabulary.

## Stories, questions and candidate questions

**1. Interview Stories** — STAR framework stories in `interview_stories` table
- Separate columns: `situation`, `task`, `action`, `result` (mandatory; enforces STAR structure)
- `strength` (1-5) — self-assessed quality of the story itself

**2. Prep Questions** — Behavioral interview questions in `interview_prep_questions`
- Linked to stories via `interview_story_questions` join table
- Each link has a `fit_score` (1-5) — how well the story answers that specific question

**3. Candidate Questions** — Questions to ask interviewers in `interview_candidate_questions`
- Categorized (Onboarding, Tech, Culture, Benefits, Logistics, Growth, Work-life)

## Shared tags

`organizer.interviews.tags` — one case-insensitive-unique vocabulary (`interview_tags`) attached to both stories (`interview_story_tag_links`) and prep questions (`interview_question_tag_links`), so the same label (e.g. `ownership`, `amazon:bias-for-action`) connects a story to the questions it fits.

- Stories and questions take `tags: list[str]` on create/update plus `POST/DELETE .../{id}/tags/{tag}`; names resolve case-insensitively to the existing tag (first spelling wins), missing ones are created
- Filter with `?tag=` on both list endpoints (`/storylist --tag`, `/preplist --tag`); `GET .../tags` on each returns only tags currently in use there
- `GET /organizer/interview-tags` (usage counts), `PATCH /{id}` (rename, 409 on name clash), `DELETE /{id}` manage the vocabulary; tags are not deleted automatically when their last story/question goes away
- The prep question detail page floats stories sharing a tag with the question to the top of the "Link a story" picker

## Question bank seed

`db/seeds/interview_prep_questions.yaml` is the versioned question bank (`text` + `tags`), loaded on every deploy by `seed_interview_prep_questions.py` from `entrypoint.sh`.

- Insert-only: missing questions are added, existing questions with no tags get the YAML tags, nothing is deleted or re-tagged.
- Matching is by exact `text`, so reword a question in the YAML and the portal together.
- A question deleted in the portal returns on the next deploy unless it is removed from the YAML too.

## Assessment scales

**Story Strength (1-5)** — quality of the story itself:
- **1 (Vague/Incomplete):** Missing context, unclear outcome, lacks details
- **2 (Basic):** STAR parts present but generic; no metrics or specifics
- **3 (Good):** Clear story, specific details, shows competency, has some measure of success
- **4 (Strong):** Specific, concrete metrics, clear before/after, demonstrates key competency well
- **5 (Excellent):** Polished, specific, quantified outcome, shows growth/learning, universally compelling

User self-assesses when creating the story. Can be revised later as the story is refined.

**Link Fit (1-5)** — how well the story answers a specific prep question:
- **1 (Poor Fit):** Tangentially related; doesn't directly answer the question
- **2 (Weak Fit):** Related but requires explanation to connect to the question
- **3 (Good Fit):** Directly addresses the question, clearly demonstrates what's being asked
- **4 (Strong Fit):** Perfectly tailored; directly and powerfully answers the question
- **5 (Excellent Fit):** Perfectly tailored; demonstrates competency exactly as the question asks

User assigns when linking a story to a prep question (default 3). Stories are sorted by `fit_score` (descending) for each question. Both scales are enforced by DB CHECK constraints.

## AI strength suggestion

`POST /organizer/interview-stories/{id}/assess-strength` (and `/storyassess <id>`) asks the LLM for a suggested 1-5 strength plus one improvement tip. It only suggests; it never writes `strength`. Returns 404 for an unknown story, 502 when the LLM fails or returns invalid JSON. Logged to `llm_calls` as `interview_story_strength`. No portal button yet.

## Command formats

Multi-field text can't be positional (resolver and MCP constraints, see [../assistant-layer.md](../assistant-layer.md#argument-parsing)):

- `/storyadd situation | task | action | result --strength 4 -t leadership,conflict` (single `text` arg, split on `|` in the handler)
- `/candidateadd How is on-call organised? --category Tech`
