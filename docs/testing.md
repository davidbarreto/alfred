# Testing

- Unit tests mock DB and external services; no real I/O. Mock all DB and external I/O; use `AsyncMock` for async repo methods.
- Use `pytest` with fixtures for DB sessions and app client.
- Test files mirror the source path, prefixed with `test_`: `tests/test_task_service.py` <- `app/features/organizer/tasks/service.py`; `tests/test_api_contacts.py` <- `app/api/routes/organizer/contacts.py`.
- One test class per logical group of behaviour (`TestComputeStreak`, `TestMissedCount`, ...).
- Aim for behaviour coverage, not line coverage: test contracts, not internals.
- Don't ignore warnings. Solve them whenever possible.
- Backend tests need `ALFRED_API_TOKEN=test-api-token` (exactly that value, the `TEST_TOKEN` in `tests/conftest.py`). `conftest.py` forces it, but if you ever see mass `401 == 200` failures, a real token in the shell is the cause: run `env -u ALFRED_API_TOKEN .venv/bin/python -m pytest` or set it to `test-api-token`. Never use another value like `test`.
- `backend/` and `web/` are separate pytest suites; run both before committing cross-cutting changes.
- For every bug fix: first write a unit test that reproduces the bug (it should fail against the unfixed code), then write the fix that makes it pass. Keep the regression test after the fix lands.

## Real-Postgres tests

The exception to "no real I/O": tests that need a real Postgres (seeded migration data, TypeDecorator bind coercion, case-insensitive SQL) are marked `@pytest.mark.db`. There are none yet: add one only when fixing a bug a mock can't reproduce. They are deselected by default and run in the CI smoke job via `pytest -m db` (`TEST_DATABASE_URL` points at the migrated DB; the `db_session` fixture rolls back). Keep them few.

## CI smoke job

`api-smoke-test.yml` runs on pushes to `main` touching `backend/` or `postman/`, next to (not blocking) the deploys. When a push adds a migration it also downgrades that many revisions and upgrades to head. Postman tests that create uniquely-named rows (tags, categories) use a per-run name, because migrations seed rows. Troubleshooting a red run (summary, logs, `api-log` artifact): `docs/operations.md`.

## Sensitive data & fixtures

- Never copy real personal or financial data (names, account/card numbers, amounts, addresses, merchant strings from a real statement, etc.) from a user-provided file into code, test fixtures, Postman collections, or documentation, even as a "quick example". Always invent synthetic equivalents that preserve the shape/format needed for the test (e.g. `"SOME PERSON"` instead of a real name, `*1234` instead of a real card suffix, round invented amounts instead of real ones).
- Treat every file the user pastes or drops for debugging (bank/card statement exports, CSVs, screenshots) as containing real third-party data by default. It's fine to read and analyze it in place; the rule is about what gets written back into the repo.
- Before committing a new fixture derived from a real file, re-read the fixture itself and confirm nothing was copy-pasted verbatim.
