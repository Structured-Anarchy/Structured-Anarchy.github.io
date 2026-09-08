from copy import deepcopy

import pytest

from scripts.make_mock_knowledge import mock_knowledge
from sitegen.knowledge import KnowledgeError, digest, empty_knowledge, local_data_path, make_origin, validate_knowledge


def test_empty_base_and_reused_cyclic_mock_are_valid():
    validate_knowledge(empty_knowledge(), lambda _: b"")
    kb, files = mock_knowledge()
    validate_knowledge(kb, files.__getitem__)
    assert len([p for p in kb["propositions"] if p["id"] == "quiet-open"]) == 1


@pytest.mark.parametrize("mutation,match", [
    (lambda k: k["propositions"][0].update(origins=[]), "non-empty"),
    (lambda k: k["propositions"][0]["origins"][0].update(start_char=999999), "invalid character range"),
    (lambda k: k["arguments"][0]["premises"][0]["origins"][0].update(first_6_chars="BROKEN"), "six characters"),
    (lambda k: k["arguments"][0]["conclusion"]["origins"][0].update(last_6_chars="BROKEN"), "six characters"),
    (lambda k: k["meanings"][-1].update(origins=[]), "non-empty"),
    (lambda k: k["propositions"][0]["bindings"][0].update(meaning_ids=[]), "non-empty"),
    (lambda k: k["propositions"][0]["bindings"][0].update(meaning_ids=["meaning-quiet-calm"]), "different symbol"),
    (lambda k: k["propositions"][1]["bindings"][1].update(excluded_meaning_ids=["meaning-quiet-calm"]), "selected and excluded"),
    (lambda k: k["propositions"][1]["bindings"][1].update(selection="specified"), "multiple meanings"),
    (lambda k: k["arguments"][0]["premises"][0].update(negated=True), "not a Horn clause"),
    (lambda k: k["arguments"][0]["conclusion"].update(proposition_id="missing"), "unknown propositions"),
    (lambda k: k["occurrences"][-1].update(session_id="session-one"), "outside its session"),
    (lambda k: k["propositions"][0].update(id=k["symbols"][0]["id"]), "duplicate id"),
    (lambda k: k["symbols"].append(dict(id="symbol-orphan", label="orphan", aliases=[])), "exactly one Normative"),
    (lambda k: k["propositions"][0]["bindings"][0].update(stop_char=999), "invalid symbol character range"),
    (lambda k: k["arguments"][0].update(probability=0.9), "Additional properties"),
])
def test_rejects_invalid_knowledge(mutation, match):
    kb, files = mock_knowledge()
    mutation(kb)
    with pytest.raises(KnowledgeError, match=match):
        validate_knowledge(kb, files.__getitem__)


def test_duplicate_rule_ignores_premise_order_and_source_occurrences():
    kb, files = mock_knowledge()
    rule = deepcopy(kb["arguments"][0])
    rule["id"] = "argument-duplicate"
    rule["premises"].reverse()
    kb["arguments"].append(rule)
    with pytest.raises(KnowledgeError, match="duplicate argument"):
        validate_knowledge(kb, files.__getitem__)


def test_hash_catches_internal_change_with_unchanged_pointer_ends():
    kb, files = mock_knowledge()
    name = kb["sources"][0]["file_name"]
    files[name] = files[name].replace(b"traffic", b"TRAFFIC")
    with pytest.raises(KnowledgeError, match="SHA-256 mismatch"):
        validate_knowledge(kb, files.__getitem__)


def test_codepoint_offsets_preserve_astral_unicode_and_crlf():
    raw = "🌿\r\ncafé and quiet\r\n".encode()
    pointer = make_origin("data/refined-transcripts/test.txt", raw, 3, 7)
    assert pointer["first_6_chars"] == "café"
    assert pointer["last_6_chars"] == "café"
    assert digest(raw) != digest(raw.replace(b"\r\n", b"\n"))


@pytest.mark.parametrize("name", ["../secret.txt", "/etc/passwd", "data/../secret.txt", "data//test.txt", "data/./test.txt", "data\\test.txt"])
def test_paths_cannot_escape_private_data(tmp_path, name):
    with pytest.raises(ValueError):
        local_data_path(tmp_path, name)


def test_symlink_escape_is_rejected(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        local_data_path(tmp_path, "data/outside/private.txt")
