"""Fictional regression graph: competing routes survive at every depth."""

from collections import Counter
from copy import deepcopy

import pytest

from sitegen.knowledge import KnowledgeError, digest, empty_knowledge, make_origin, validate_knowledge


def competing_knowledge():
    statements = {
        "marked-passable": "Every marked gate is passable.",
        "marked-unlocked": "Every marked gate is unlocked.",
        "unlocked-passable": "Every unlocked gate is passable.",
        "marked-bypass": "Every marked gate has a bypass route.",
        "bypass-passable": "Every gate with a bypass route is passable.",
        "north-marked": "The north gate is marked.",
        "north-impassable": "The north gate is impassable.",
        "south-marked": "The south gate is marked.",
        "south-impassable": "The south gate is impassable.",
        "north-unlocked": "The north gate is unlocked.",
        "unlocked-bypass": "Every unlocked gate has a bypass route.",
    }
    routes = [
        ("marked-unlocked-route", ["marked-unlocked", "unlocked-passable"], "marked-passable", False),
        ("marked-bypass-route", ["marked-bypass", "bypass-passable"], "marked-passable", False),
        ("north-counterexample", ["north-marked", "north-impassable"], "marked-passable", True),
        ("south-counterexample", ["south-marked", "south-impassable"], "marked-passable", True),
        ("unlocked-bypass-route", ["unlocked-bypass", "bypass-passable"], "unlocked-passable", False),
        ("unlocked-counterexample", ["north-unlocked", "north-impassable"], "unlocked-passable", True),
    ]
    arguments = [
        "Given " + " and ".join(statements[p] for p in premises)
        + ", it follows that " + ("it is false that " if negated else "") + statements[head]
        for _, premises, head, negated in routes
    ]
    text = "Fictional gate debate; not session content.\n" + "\n".join([*statements.values(), *arguments])
    raw = text.encode()
    name = "data/refined-transcripts/fictional-gates.txt"
    kb = empty_knowledge()
    kb["sources"].append(dict(id="source-gates", file_name=name, sha256=digest(raw), label="Fictional gates"))
    kb["sessions"].append(dict(id="session-gates", title="Fictional gates", source_ids=["source-gates"]))

    def origins(quote):
        start = text.index(quote)
        return [make_origin(name, raw, start, start + len(quote))]

    def occurrence(identifier, kind, evidence):
        kb["occurrences"].append(dict(id="occ-" + identifier, target_type=kind, target_id=identifier,
            session_id="session-gates", stance="asserted", origins=deepcopy(evidence)))

    for pid, assertion in statements.items():
        evidence = origins(assertion)
        kb["propositions"].append(dict(id=pid, text=assertion, scope="The fictional gates.",
            kind="empirical", thesis=pid == "marked-passable", topics=["Fictional access"],
            origins=evidence, bindings=[]))
        occurrence(pid, "proposition", evidence)
    for (aid, premises, head, negated), passage in zip(routes, arguments):
        evidence = origins(passage)
        kb["arguments"].append(dict(id=aid, premises=[dict(proposition_id=p, negated=False,
            origins=origins(statements[p])) for p in premises],
            conclusion=dict(proposition_id=head, negated=negated, origins=evidence),
            explicitness="explicit", explanation="A distinct fictional route, not a truth verdict.", origins=evidence))
        occurrence(aid, "argument", evidence)
    return kb, {name: raw}


def test_independent_opposing_routes_survive_on_thesis_and_premise():
    kb, files = competing_knowledge()
    validate_knowledge(kb, files.__getitem__)
    counts = Counter((a["conclusion"]["proposition_id"], a["conclusion"]["negated"]) for a in kb["arguments"])
    assert counts == {
        ("marked-passable", False): 2, ("marked-passable", True): 2,
        ("unlocked-passable", False): 1, ("unlocked-passable", True): 1,
    }
    assert all(len(a["premises"]) == 2 for a in kb["arguments"])


@pytest.mark.parametrize("index", range(6))
def test_repeated_route_is_rejected_even_when_opposing_routes_exist(index):
    kb, files = competing_knowledge()
    repeated = deepcopy(kb["arguments"][index])
    repeated["id"] = "repeated-route"
    repeated["premises"].reverse()
    kb["arguments"].append(repeated)
    with pytest.raises(KnowledgeError, match="duplicate argument"):
        validate_knowledge(kb, files.__getitem__)
