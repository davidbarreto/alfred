import pytest
from app.utils.nlp import clean_text, extract_entities, normalize_date

def test_clean_text():
    assert clean_text("remind me to buy milk") == "buy milk"
    assert clean_text("please call the doctor thanks") == "call the doctor"
    assert clean_text("  i need to   fix the car  ") == "fix the car"

def test_normalize_date():
    # Basic format check (dateparser result depends on 'today')
    res = normalize_date("tomorrow")
    assert res is not None
    assert len(res) == 10  # YYYY-MM-DD
    
    assert normalize_date("2025-12-25") == "2025-12-25"
    assert normalize_date("") is None

def test_extract_entities_priority():
    text = "buy milk urgently"
    clean, entities = extract_entities(text)
    assert clean == "buy milk"
    assert entities["priority"] == "high"

def test_extract_entities_date():
    text = "call mom next monday"
    clean, entities = extract_entities(text)
    assert clean == "call mom"
    assert "deadline" in entities

def test_extract_complex_string():
    text = "remind me to finish the report asap by friday"
    clean, entities = extract_entities(text)
    assert clean == "finish the report"
    assert entities["priority"] == "high"
    assert "deadline" in entities