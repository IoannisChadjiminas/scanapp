import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "printing_family_probe", Path(__file__).resolve().parents[1]/"scripts/printing_family_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_probe_reads_a_saved_api_response_in_shown_order():
    response = {
        "best_match": {"card_id": "ja:M6a-137"},
        "alternatives": [{"card_id": "ja:S10P-030"}, {"card_id": "ja:M6a-137"}],
        "printing_review": {"plausible_printings": [{"card_id": "ja:CP6-011"}]},
        "visual_top20": [{"card_id": "ja:S8a-P-001"}],
    }
    assert probe.response_ids(response) == ["ja:M6a-137", "ja:S10P-030", "ja:CP6-011", "ja:S8a-P-001"]


def test_probe_reads_lists_and_reports_an_empty_response():
    assert probe.response_ids(["a", {"card_id": "b"}, "a"]) == ["a", "b"]
    assert probe.response_ids({"best_match": None, "alternatives": []}) == []
