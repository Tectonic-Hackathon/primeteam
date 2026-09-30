"""Checks every demo question in datasets/payroll_cutoff/demo_questions.json against the engine."""
import json

import pytest
from fastapi.testclient import TestClient

import db
from main import app

QUESTIONS = json.loads((db.DATASETS / "payroll_cutoff" / "demo_questions.json").read_text(encoding="utf-8"))["questions"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    original = db.DB_PATH
    db.DB_PATH = tmp_path_factory.mktemp("cutoff") / "test.sqlite3"
    with TestClient(app) as test_client:
        yield test_client
    db.DB_PATH = original


def test_dataset_is_seeded_next_to_atlas(client):
    ids = {s["id"] for s in client.get("/api/sources").json()["sources"]}
    assert {"be-cutoff-v3", "be-cutoff-v1", "be-client-service-faq", "teams-fr-consultants"} <= ids
    assert "be-procedure-v2" in ids  # the original Atlas demo is still there


def test_demo_questions_endpoint(client):
    listed = client.get("/api/demo-questions").json()["questions"]
    assert [q["id"] for q in listed] == [q["id"] for q in QUESTIONS]


@pytest.mark.parametrize("case", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_demo_question(client, case):
    payload = {k: case[k] for k in ("question", "country", "domain", "as_of")}
    payload |= {"client": case["client"] or None, "project": case["project"] or None}
    result = client.post("/api/query", json=payload).json()
    expect = case["expect"]
    claim_sources = [e["source_id"] for e in result["evidence"]]
    experts = [e["name"] for e in result["experts"]]
    if "status" in expect:
        assert result["status"] == expect["status"]
    if "claims" in expect:
        assert len(result["claims"]) == expect["claims"]
    if "first_claim_source" in expect:
        assert claim_sources[0] == expect["first_claim_source"]
    if "first_claim_contains" in expect:
        assert expect["first_claim_contains"] in result["claims"][0]["text"]
    for component, status in expect.get("completeness", {}).items():
        assert {"component": component, "status": status} in [{k: c[k] for k in ("component", "status")} for c in result["completeness"]]
    for kind in expect.get("review_kinds", []):
        assert kind in {r["kind"] for r in result["review_items"]}
    for source_id in expect.get("excluded_sources", []):
        assert source_id in {x["source_id"] for x in result["exclusions"]}
    for source_id in expect.get("claims_never_from", []):
        assert source_id not in claim_sources
    if "experts" in expect:
        assert experts[:len(expect["experts"])] == expect["experts"] if expect["experts"] else experts == []
    for name in expect.get("experts_never", []):
        assert name not in experts
    # Review items must belong to this dataset, never to the Atlas demo.
    atlas = {"be-procedure-v2", "be-procedure-v1", "teams-override", "meeting-change", "be-checklist-copy"}
    assert not {sid for r in result["review_items"] for sid in r["source_ids"]} & atlas
