from app.assistant.intents.intent_examples import INTENT_EXAMPLES, IntentExample

_KNOWN_INTENTS = {
    "task.add",
    "task.list",
    "task.update",
    "task.complete",
    "task.delete",
    "note.add",
    "note.search",
    "note.list",
    "note.update",
    "note.delete",
    "event.add",
    "event.list",
    "event.update",
    "event.delete",
    "finance.transaction_add",
    "finance.transaction_list",
    "finance.spending_report",
    "finance.spending_average",
    "finance.spending_top",
    "finance.budget_add",
    "finance.budget_list",
    "finance.budget_remaining",
    "finance.balance_forecast",
    "unknown",
}


class TestIntentExamples:
    def test_all_examples_are_intent_example_instances(self):
        for ex in INTENT_EXAMPLES:
            assert isinstance(ex, IntentExample)

    def test_no_empty_text(self):
        for ex in INTENT_EXAMPLES:
            assert ex.text.strip(), f"Empty text for intent '{ex.intent}'"

    def test_no_empty_intent(self):
        for ex in INTENT_EXAMPLES:
            assert ex.intent.strip(), f"Empty intent for text '{ex.text}'"

    def test_all_intents_are_known(self):
        unexpected = {ex.intent for ex in INTENT_EXAMPLES} - _KNOWN_INTENTS
        assert not unexpected, f"Unexpected intent labels: {unexpected}"

    def test_all_known_intents_are_covered(self):
        present = {ex.intent for ex in INTENT_EXAMPLES}
        missing = _KNOWN_INTENTS - present
        assert not missing, f"Missing intent labels: {missing}"

    def test_no_duplicate_text_per_intent(self):
        seen: set[tuple[str, str]] = set()
        for ex in INTENT_EXAMPLES:
            key = (ex.intent, ex.text)
            assert key not in seen, f"Duplicate example: intent='{ex.intent}' text='{ex.text}'"
            seen.add(key)

    def test_minimum_examples_per_intent(self):
        from collections import Counter
        counts = Counter(ex.intent for ex in INTENT_EXAMPLES)
        sparse = {intent: n for intent, n in counts.items() if n < 3}
        assert not sparse, f"Intents with fewer than 3 examples: {sparse}"

    def test_ids_are_unique(self):
        ids = [ex.id for ex in INTENT_EXAMPLES]
        duplicates = {i for i in ids if ids.count(i) > 1}
        assert not duplicates, f"Duplicate IDs: {duplicates}"

    def test_ids_are_sequential_from_one(self):
        ids = sorted(ex.id for ex in INTENT_EXAMPLES)
        assert ids == list(range(1, len(INTENT_EXAMPLES) + 1))
