from copy import deepcopy

import pytest

from scripts.make_mock_knowledge import add_induced_mock, mock_knowledge
from sitegen.knowledge import KnowledgeError, digest, empty_knowledge, local_data_path, make_origin, validate_knowledge


def test_empty_base_and_reused_cyclic_mock_are_valid():
    validate_knowledge(empty_knowledge(), lambda _: b"")
    kb, files = mock_knowledge()
    validate_knowledge(kb, files.__getitem__)
    assert len([p for p in kb["propositions"] if p["id"] == "quiet-open"]) == 1


@pytest.mark.parametrize("mutation,match", [
    (lambda q: q.pop("session_id"), "session_id.*required"),
    (lambda q: q.update(session_id="missing"), "unknown sessions"),
    (lambda q: q.update(session_id="session-one"), "question evidence is outside its session"),
    (lambda q: q.update(origin_kind="guessed"), "not one of"),
])
def test_session_questions_require_valid_session_provenance(mutation, match):
    kb, files = mock_knowledge()
    mutation(kb["questions"][0])
    with pytest.raises(KnowledgeError, match=match):
        validate_knowledge(kb, files.__getitem__)


@pytest.mark.parametrize("kind", [None, "extraction_review"])
def test_review_and_legacy_questions_remain_recoverable(kind):
    kb, files = mock_knowledge()
    question = kb["questions"][0]
    question.pop("session_id")
    question.pop("origin_kind")
    if kind:
        question["origin_kind"] = kind
    validate_knowledge(kb, files.__getitem__)


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


def induced_fixture():
    kb, files = mock_knowledge()
    add_induced_mock(kb, files)
    return kb, files


def test_induced_premise_has_context_not_invented_assertion():
    kb, files = induced_fixture()
    validate_knowledge(kb, files.__getitem__)
    induced = kb["propositions"][-1]
    assert induced["origins"] == induced["bindings"][0]["origins"] == []
    assert not any(o["target_id"] == induced["id"] for o in kb["occurrences"])


@pytest.mark.parametrize("mutation,match", [
    (lambda k: k["arguments"][-1].update(premises=k["arguments"][-1]["premises"][1:]), "source-substantiated"),
    (lambda k: k["arguments"][-1].update(explicitness="explicit"), "must be reconstructed"),
    (lambda k: k["propositions"][-1]["induction"].update(argument_ids=["argument-cycle"]), "using this premise"),
    (lambda k: k["propositions"][-1]["induction"].update(context_origins=[]), "non-empty"),
    (lambda k: k["arguments"][-1]["premises"][0].update(origins=[]), "sourced literal requires origins"),
    (lambda k: k["propositions"][0]["bindings"][0].update(origins=[]), "sourced symbol binding"),
    (lambda k: k["occurrences"][-1].update(target_type="proposition", target_id="study-open"), "cannot have an asserted"),
    (lambda k: k["propositions"][-1].update(origins=k["propositions"][-1]["induction"]["context_origins"]), "expected to be empty"),
])
def test_induced_rules_do_not_relax_sourced_provenance(mutation, match):
    kb, files = induced_fixture()
    mutation(kb)
    with pytest.raises(KnowledgeError, match=match):
        validate_knowledge(kb, files.__getitem__)


def test_induced_atom_can_be_challenged_without_inventing_assertion():
    kb, files = induced_fixture()
    context = kb["propositions"][-1]["induction"]["context_origins"]
    # Schema test only: semantic warrant for a denial is reviewed separately.
    kb["occurrences"].append(dict(id="occurrence-challenge", target_type="proposition", target_id="study-open",
                                  session_id="session-two", stance="rejected", origins=deepcopy(context)))
    validate_knowledge(kb, files.__getitem__)


def test_induced_atom_can_gain_assertion_evidence_without_losing_history():
    kb, files = induced_fixture()
    proposition = kb["propositions"][-1]
    history = deepcopy(proposition["induction"])
    # A later fictional session actually states the previously missing policy.
    name = "data/refined-transcripts/mock-three.txt"
    files[name] = proposition["text"].encode()
    origin = make_origin(name, files[name], 0, len(proposition["text"]))
    kb["sources"].append(dict(id="source-three", file_name=name, sha256=digest(files[name]), label="Fictional session three"))
    kb["sessions"].append(dict(id="session-three", title="Fictional session three", source_ids=["source-three"]))
    proposition.update(evidence_status="sourced", origins=[origin])
    for binding in proposition["bindings"]:
        binding["origins"] = [deepcopy(origin)]
    for argument in kb["arguments"]:
        for literal in [*argument["premises"], argument["conclusion"]]:
            if literal["proposition_id"] == proposition["id"]:
                literal["origins"] = [deepcopy(origin)]
    kb["occurrences"].append(dict(id="occurrence-policy-stated", target_type="proposition",
        target_id=proposition["id"], session_id="session-three", stance="asserted", origins=[origin]))
    validate_knowledge(kb, files.__getitem__)
    assert proposition["induction"] == history
    assert proposition["origins"] != history["context_origins"]
