from unittest.mock import AsyncMock

import pytest

from app.integrations.google_contacts.provider import GoogleContactsProvider


@pytest.fixture
def provider():
    return GoogleContactsProvider(client=AsyncMock())


class TestToPerson:
    def test_website_included_when_present(self, provider):
        person, update_fields = provider._to_person({"website": "https://linkedin.com/in/alice"})
        assert person["urls"] == [{"value": "https://linkedin.com/in/alice", "type": "other"}]
        assert "urls" in update_fields

    def test_website_cleared_when_falsy(self, provider):
        person, update_fields = provider._to_person({"website": None})
        assert person["urls"] == []
        assert "urls" in update_fields

    def test_website_omitted_when_key_absent(self, provider):
        person, update_fields = provider._to_person({"name": "Alice"})
        assert "urls" not in person
        assert "urls" not in update_fields


class TestFromPerson:
    def test_website_extracted_from_urls(self):
        provider = GoogleContactsProvider(client=AsyncMock())
        person = {
            "resourceName": "people/c1",
            "names": [{"displayName": "Alice"}],
            "urls": [{"value": "https://linkedin.com/in/alice", "type": "other"}],
        }
        record = provider._from_person(person)
        assert record["website"] == "https://linkedin.com/in/alice"

    def test_website_none_when_no_urls(self):
        provider = GoogleContactsProvider(client=AsyncMock())
        person = {"resourceName": "people/c2", "names": [{"displayName": "Bob"}]}
        record = provider._from_person(person)
        assert record["website"] is None
