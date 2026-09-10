"""Fictional Boolean graphs; exact inference checked against full enumeration."""

from copy import deepcopy
from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import minimize
from scipy.special import logsumexp

from sitegen.inference import (
    GAP_TOLERANCE, ExactMarginals, Feature, InferenceError, atom_priors,
    components, features_for, infer, validate_inference,
)


def graph(routes, *, induced=(), extra=()):
    """Minimal solver inputs, not extraction fixtures or session assertions."""
    ids = sorted({pid for premises, head in routes for pid, _ in [*premises, head]} | set(extra))
    return {
        "propositions": [dict(id=pid, evidence_status="induced" if pid in induced else "sourced",
                              origins=[] if pid in induced else ["fictional source"]) for pid in ids],
        "arguments": [dict(id=f"clause-{i}", premises=[dict(proposition_id=p, negated=n) for p, n in premises],
                           conclusion=dict(proposition_id=head[0], negated=head[1]))
                      for i, (premises, head) in enumerate(routes)],
    }


def opposition(m=1, n=1, *, flat=False):
    support = [(f"support-{i}", False) for i in range(m)]
    refute = [(f"refute-{i}", False) for i in range(n)]
    return graph([(support, ("thesis", False)), (refute, ("thesis", True))],
                 induced=[p for p, _ in support + refute] if flat else [])


def enumeration(kb, ids):
    """Independent truth evaluation, without using Feature.table or elimination."""
    priors = atom_priors(kb)
    clauses = sorted(kb["arguments"], key=lambda a: a["id"])
    worlds = np.array(list(product((0, 1), repeat=len(ids))))
    columns, coefficients = [], []
    for clause in clauses:
        antecedent = np.ones(len(worlds), dtype=bool)
        for literal in clause["premises"]:
            antecedent &= worlds[:, ids.index(literal["proposition_id"])] == (not literal["negated"])
        head = clause["conclusion"]
        consequent = worlds[:, ids.index(head["proposition_id"])] == (not head["negated"])
        columns.append(~antecedent | consequent)
        coefficients.append(6.2)
    for pid in ids:
        if priors[pid] == "substantiated-leaf":
            columns.extend([worlds[:, ids.index(pid)], 1 - worlds[:, ids.index(pid)]])
            coefficients.extend([4, 1])
    matrix = np.array(columns, dtype=float).T
    return worlds, matrix, np.array(coefficients)


@pytest.mark.parametrize("kb", [
    opposition(), opposition(2, 1), opposition(1, 2, flat=True),
    graph([([("a", False)], ("b", False)), ([("b", False)], ("c", True)), ([("c", False)], ("a", False))]),
    graph([([("a", True)], ("b", True)), ([("a", False), ("c", False)], ("b", False))]),
    graph([([("a", False)], ("a", True))]),
])
def test_elimination_and_gradient_match_enumeration(kb):
    ids = sorted(p["id"] for p in kb["propositions"])
    features = features_for(ids, sorted(kb["arguments"], key=lambda a: a["id"]), atom_priors(kb))
    program = ExactMarginals(len(ids), features)
    worlds, matrix, _ = enumeration(kb, ids)
    weights = np.linspace(0.2, 12, len(features))
    log_z, means, atoms = program.evaluate(weights)
    scores = matrix @ weights
    p = np.exp(scores - logsumexp(scores))
    assert log_z == pytest.approx(logsumexp(scores), abs=1e-12)
    np.testing.assert_allclose(means, p @ matrix, atol=1e-12)
    np.testing.assert_allclose(atoms, p @ worlds, atol=1e-12)
    for i in range(len(weights)):
        change = np.eye(1, len(weights), i)[0] * 1e-5
        derivative = (program.evaluate(weights + change)[0] - program.evaluate(weights - change)[0]) / 2e-5
        assert derivative == pytest.approx(means[i], abs=1e-8)


@pytest.mark.parametrize("m,n,expected", [(1, 1, .5), (2, 1, .400322293), (1, 2, .599677707), (3, 1, .364036471)])
def test_discussed_flat_leaf_examples(m, n, expected):
    kb = opposition(m, n, flat=True)
    report = infer(kb)
    assert report["probabilities"]["thesis"] == pytest.approx(expected, abs=1e-7)
    validate_inference(kb, report)


def test_sourced_leaves_anchor_opposing_premises_without_forcing_clause_means():
    kb = opposition()
    report = infer(kb)
    assert report["probabilities"]["thesis"] == pytest.approx(.5, abs=1e-7)
    assert report["probabilities"]["support-0"] > .2510064
    assert report["probabilities"]["refute-0"] > .2510064
    ids = sorted(report["probabilities"])
    worlds, matrix, coefficients = enumeration(kb, ids)
    def objective(w):
        scores = matrix @ w
        z = logsumexp(scores)
        p = np.exp(scores-z)
        return z - coefficients @ np.log(w), p @ matrix - coefficients/w
    fit = minimize(objective, coefficients.copy(), jac=True, method="L-BFGS-B",
                   bounds=[(float(c), None) for c in coefficients], options={"gtol": 1e-10, "ftol": 1e-15})
    p = np.exp(matrix @ fit.x - logsumexp(matrix @ fit.x))
    np.testing.assert_allclose([report["probabilities"][pid] for pid in ids], p @ worlds, atol=1e-7)
    assert all(group["duality_gap"] <= GAP_TOLERANCE for group in report["components"])


def test_leaf_prior_is_once_per_atom_and_both_signed_conclusions_make_nonleaves():
    kb = graph([
        ([("shared", False), ("induced", False)], ("first", False)),
        ([("shared", False)], ("second", False)),
        ([("first", False)], ("second", True)),
        ([("challenge", False)], ("induced", True)),
    ], induced=["induced"])
    priors = atom_priors(kb)
    assert priors == dict(challenge="substantiated-leaf", first="none", induced="none", second="none", shared="substantiated-leaf")
    ids, clauses = components(kb)[0]
    features = features_for(ids, clauses, priors)
    assert len(features) == len(clauses) + 4  # Two leaf priors, not one per use.


def test_components_do_not_split_shared_premises_and_singletons_are_unanchored():
    kb = graph([([("shared", False)], ("a", False)), ([("shared", False)], ("b", True)),
                ([("other", False)], ("c", False))], extra=["isolated"])
    original = deepcopy(kb)
    report = infer(kb)
    assert kb == original
    assert sorted(len(g["atom_ids"]) for g in report["components"]) == [1, 2, 3]
    assert report["probabilities"]["isolated"] == .5
    for ids, clauses in components(kb):
        separate = dict(propositions=[p for p in kb["propositions"] if p["id"] in ids], arguments=clauses)
        assert infer(separate)["probabilities"] == {pid: report["probabilities"][pid] for pid in ids}
    validate_inference(kb, report)


def test_cycle_has_no_leaf_priors_and_results_ignore_input_order():
    kb = graph([([("a", False)], ("b", False)), ([("b", False)], ("a", False))])
    report = infer(kb)
    assert set(report["priors"].values()) == {"none"}
    assert report["probabilities"] == pytest.approx(dict(a=.5, b=.5), abs=1e-7)
    kb["propositions"].reverse()
    kb["arguments"].reverse()
    assert infer(kb)["probabilities"] == report["probabilities"]


def test_exact_elimination_handles_a_large_sparse_component():
    kb = graph([([(f"atom-{i}", False)], (f"atom-{i+1}", False)) for i in range(50)])
    report = infer(kb)
    assert len(report["components"]) == 1
    assert report["components"][0]["elimination_width"] == 1
    assert len(report["probabilities"]) == 51  # Never constructs 2**51 worlds.
    validate_inference(kb, report)


def test_resource_limit_is_checked_before_factor_allocation():
    with pytest.raises(InferenceError, match="state limit"):
        ExactMarginals(30, [Feature(tuple(range(30)), (0,)*30, 6.2)])
    with pytest.raises(InferenceError, match="state limit"):
        infer(opposition(3, 2), max_factor_states=4)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(graph_sha256="wrong"),
    lambda r: r["probabilities"].update(thesis=float("nan")),
    lambda r: r["probabilities"].pop("thesis"),
    lambda r: r["model"].update(entropy_weight=2),
    lambda r: r["model"]["clause_prior"].__setitem__(0, 9),
    lambda r: r["components"][0]["probabilities"].update(thesis=.1),
    lambda r: r["components"][0].update(weights=[1.] * len(r["components"][0]["weights"]), duality_gap=0),
    lambda r: r["components"].clear(),
])
def test_invalid_or_stale_results_are_rejected(mutation):
    kb = opposition()
    report = infer(kb)
    mutation(report)
    with pytest.raises(InferenceError):
        validate_inference(kb, report)


def test_unconverged_optimizer_is_not_published(monkeypatch):
    monkeypatch.setattr("sitegen.inference.minimize", lambda *args, **kwargs: SimpleNamespace(x=np.array(args[1]), nit=0))
    with pytest.raises(InferenceError, match="did not converge"):
        infer(opposition())


def test_empty_graph():
    kb = dict(propositions=[], arguments=[])
    report = infer(kb)
    assert report["probabilities"] == {}
    validate_inference(kb, report)
