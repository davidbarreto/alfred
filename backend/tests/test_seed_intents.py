from db.seeds.seed_intents import stable_source_id


class TestStableSourceId:
    def test_returns_int(self):
        result = stable_source_id("task.add", "Remind me to call John")
        assert isinstance(result, int)

    def test_deterministic(self):
        a = stable_source_id("task.list", "Show my tasks")
        b = stable_source_id("task.list", "Show my tasks")
        assert a == b

    def test_different_inputs_produce_different_ids(self):
        a = stable_source_id("task.add", "Buy groceries")
        b = stable_source_id("task.add", "Call the dentist")
        c = stable_source_id("note.add", "Buy groceries")
        assert a != b
        assert a != c

    def test_fits_in_signed_32_bit_range(self):
        for intent, text in [
            ("task.add", "Remind me to call John tomorrow"),
            ("unknown", "What's the weather today?"),
            ("finance.transaction_add", "I spent 45 at the supermarket"),
        ]:
            result = stable_source_id(intent, text)
            assert -(2**31) <= result < 2**31, f"Out of int32 range: {result}"

    def test_intent_changes_id(self):
        text = "Show my list"
        a = stable_source_id("task.list", text)
        b = stable_source_id("note.list", text)
        assert a != b
