"""Component-wise maximum entropy, separate from extraction and provenance.

For indicator features f and positive coefficients c, maximize
    H(p) + sum(c * log(E_p[f])).
The convex dual is log Z(w) - sum(c * log(w)) + sum(c * (log(c)-1)).
Its gradient is E_w[f] - c/w, with p_w(x) proportional to exp(sum(w*f)).
Exact variable elimination and its reverse pass compute Z and all marginals;
we never enumerate a component's complete joint table or sample its worlds.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

import numpy as np
from scipy.optimize import minimize

MODEL = {
    "id": "maxent-beta-v1", "entropy_weight": 1,
    "clause_prior": [7.2, 1], "induced_leaf_prior": [1, 1],
    "substantiated_leaf_prior": [5, 2],
    "leaf_rule": "used-as-premise-with-no-signed-incoming-clause",
}
GAP_TOLERANCE = 1e-10
MAX_FACTOR_STATES = 262_144
MAX_TOTAL_STATES = 4_194_304


class InferenceError(ValueError):
    """Do not publish stale, unconverged or resource-truncated estimates."""


def graph_digest(kb: dict) -> str:
    raw = json.dumps(kb, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def components(kb: dict) -> list[tuple[list[str], list[dict]]]:
    """Undirected factor connectivity, not per-thesis ancestor trees."""
    neighbors = {p["id"]: set() for p in kb["propositions"]}
    for clause in kb["arguments"]:
        ids = {lit["proposition_id"] for lit in [*clause["premises"], clause["conclusion"]]}
        head = clause["conclusion"]["proposition_id"]
        for pid in ids:
            neighbors[head].add(pid)
            neighbors[pid].add(head)
    groups, visited = [], set()
    membership = {}
    for pid in sorted(neighbors):
        if pid in visited:
            continue
        pending, group = [pid], set()
        while pending:
            current = pending.pop()
            if current in group:
                continue
            group.add(current)
            pending.extend(neighbors[current] - group)
        visited.update(group)
        for current in group:
            membership[current] = len(groups)
        groups.append((sorted(group), []))
    for clause in sorted(kb["arguments"], key=lambda a: a["id"]):
        groups[membership[clause["conclusion"]["proposition_id"]]][1].append(clause)
    return groups


def atom_priors(kb: dict) -> dict[str, str]:
    incoming = {a["conclusion"]["proposition_id"] for a in kb["arguments"]}
    premises = {p["proposition_id"] for a in kb["arguments"] for p in a["premises"]}
    result = {}
    for atom in kb["propositions"]:
        pid = atom["id"]
        if pid not in premises or pid in incoming:
            result[pid] = "none"
        elif atom.get("evidence_status") == "induced":
            result[pid] = "induced-leaf"
        elif atom.get("origins"):
            result[pid] = "substantiated-leaf"
        else:
            raise InferenceError("A leaf premise has no substantiation or induction classification")
    return result


@dataclass(frozen=True)
class Feature:
    scope: tuple[int, ...]
    false_assignment: tuple[int, ...]
    coefficient: float

    def table(self) -> np.ndarray:
        table = np.ones((2,) * len(self.scope))
        table[self.false_assignment] = 0
        return table


def features_for(ids: list[str], clauses: list[dict], priors: dict[str, str]) -> list[Feature]:
    positions = {pid: i for i, pid in enumerate(ids)}
    features = []
    for clause in clauses:
        # A material implication is false exactly when every antecedent is true
        # and its signed consequent is false. Negation never creates a new atom.
        violation = {positions[p["proposition_id"]]: int(not p["negated"]) for p in clause["premises"]}
        head = clause["conclusion"]
        variable, value = positions[head["proposition_id"]], int(head["negated"])
        if variable in violation and violation[variable] != value:
            raise InferenceError("Tautological clauses must be removed during graph validation")
        violation[variable] = value
        scope = tuple(sorted(violation))
        features.append(Feature(scope, tuple(violation[v] for v in scope), 6.2))
    for pid in ids:
        if priors[pid] == "substantiated-leaf":
            features.extend([Feature((positions[pid],), (0,), 4), Feature((positions[pid],), (1,), 1)])
    return features


@dataclass(frozen=True)
class Elimination:
    inputs: tuple[int, ...]
    scope: tuple[int, ...]
    axis: int
    output: int


class ExactMarginals:
    """A reusable elimination program with reverse-mode marginal computation."""

    def __init__(self, atom_count: int, features: list[Feature], *, max_factor_states: int = MAX_FACTOR_STATES):
        self.features = features
        self.scopes = [f.scope for f in features] + [(i,) for i in range(atom_count)]
        if any(2 ** len(scope) > max_factor_states for scope in self.scopes):
            raise InferenceError("Exact inference factor exceeds the configured state limit")
        active = set(range(len(self.scopes)))
        adjacency = {i: set() for i in range(atom_count)}
        for scope in self.scopes:
            for i in scope:
                adjacency[i].update(set(scope) - {i})
        self.steps = []
        self.width = 0
        total_states = sum(2 ** len(scope) for scope in self.scopes)
        while adjacency:
            def cost(i):
                neighbors = adjacency[i]
                fill = sum(len(neighbors - adjacency[j] - {j}) for j in neighbors) // 2
                return fill, len(neighbors), i

            variable = min(adjacency, key=cost)
            neighbors = adjacency.pop(variable)
            for i in neighbors:
                adjacency[i].update(neighbors - {i})
                adjacency[i].discard(variable)
            inputs = tuple(sorted(i for i in active if variable in self.scopes[i]))
            scope = tuple(sorted({v for i in inputs for v in self.scopes[i]}))
            self.width = max(self.width, len(scope) - 1)
            total_states += 2 ** len(scope)
            if 2 ** len(scope) > max_factor_states or total_states > MAX_TOTAL_STATES:
                raise InferenceError("Exact inference exceeds the configured state limit; no estimates were published")
            output = len(self.scopes)
            self.steps.append(Elimination(inputs, scope, scope.index(variable), output))
            self.scopes.append(tuple(v for v in scope if v != variable))
            active.difference_update(inputs)
            active.add(output)
        self.roots = sorted(active)
        self.atom_count = atom_count
        self.tables = [f.table() for f in features]

    def evaluate(self, weights: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        values = [w * table for w, table in zip(weights, self.tables)]
        # Zero unary potentials let the same reverse pass recover every atom.
        values.extend(np.zeros(2) for _ in range(self.atom_count))
        joints = []
        for step in self.steps:
            joint = np.zeros((2,) * len(step.scope))
            for i in step.inputs:
                shape = tuple(2 if v in self.scopes[i] else 1 for v in step.scope)
                joint += values[i].reshape(shape)
            joints.append(joint)
            values.append(np.logaddexp.reduce(joint, axis=step.axis))
        log_z = float(sum(values[i] for i in self.roots))
        adjoints: list[Any] = [None] * len(values)
        for i in self.roots:
            adjoints[i] = np.ones_like(values[i])
        for step, joint in reversed(list(zip(self.steps, joints))):
            conditional = np.exp(joint - np.expand_dims(values[step.output], step.axis))
            marginal = conditional * np.expand_dims(adjoints[step.output], step.axis)
            for i in step.inputs:
                axes = tuple(axis for axis, v in enumerate(step.scope) if v not in self.scopes[i])
                adjoints[i] = marginal.sum(axis=axes)
        means = np.array([np.sum(adjoints[i] * table) for i, table in enumerate(self.tables)])
        atoms = np.array([adjoints[len(self.features) + i][1] for i in range(self.atom_count)])
        return log_z, means, atoms


def certificate(program: ExactMarginals, weights: np.ndarray) -> dict:
    log_z, means, atoms = program.evaluate(weights)
    coefficients = np.array([f.coefficient for f in program.features])
    if not np.isfinite(log_z) or not np.all(np.isfinite(atoms)) or not np.all(np.isfinite(means)) or np.any(means <= 0):
        raise InferenceError("Inference produced non-finite probabilities")
    # Fenchel duality gap: sum c * (r - 1 - log(r)), r = w E[f]/c.
    # Computing via log1p avoids cancellation near the optimum.
    residual = weights * means / coefficients - 1
    gap = float(np.sum(coefficients * (residual - np.log1p(residual))))
    if not math.isfinite(gap):
        raise InferenceError("Inference produced a non-finite optimality certificate")
    entropy = float(log_z - weights @ means)
    return dict(atoms=atoms, means=means, duality_gap=max(0.0, gap), entropy=entropy,
                objective=float(entropy + coefficients @ np.log(means)))


def solve_component(ids: list[str], clauses: list[dict], priors: dict[str, str], **limits) -> dict:
    features = features_for(ids, clauses, priors)
    program = ExactMarginals(len(ids), features, **limits)
    coefficients = np.array([f.coefficient for f in features])
    iterations = 0
    weights = coefficients.copy()
    if features:
        def objective(w):
            log_z, means, _ = program.evaluate(w)
            return log_z - coefficients @ np.log(w), means - coefficients / w

        fit = minimize(objective, weights, jac=True, method="L-BFGS-B",
                       bounds=[(float(c), None) for c in coefficients],
                       options={"gtol": 1e-10, "ftol": 1e-15, "maxiter": 2000, "maxls": 50})
        weights = fit.x
        iterations = int(fit.nit)
    result = certificate(program, weights)
    if not math.isfinite(result["duality_gap"]) or result["duality_gap"] > GAP_TOLERANCE:
        raise InferenceError("Maximum-entropy optimization did not converge; no estimates were published")
    return {
        "atom_ids": ids, "clause_ids": [a["id"] for a in clauses],
        "probabilities": dict(zip(ids, map(float, result["atoms"]))),
        "clause_probabilities": dict(zip((a["id"] for a in clauses), map(float, result["means"][:len(clauses)]))),
        "weights": list(map(float, weights)), "method": "exact-variable-elimination",
        "elimination_width": program.width, "iterations": iterations,
        "duality_gap": result["duality_gap"], "entropy": result["entropy"], "objective": result["objective"],
    }


def infer(kb: dict, **limits) -> dict:
    """Input must already pass knowledge/provenance validation. Never mutate it."""
    priors = atom_priors(kb)
    solved = [solve_component(ids, clauses, priors, **limits) for ids, clauses in components(kb)]
    return {
        "version": 1, "model": deepcopy(MODEL), "graph_sha256": graph_digest(kb),
        "priors": priors, "probabilities": {pid: p for group in solved for pid, p in group["probabilities"].items()},
        "components": solved,
    }


def validate_inference(kb: dict, report: dict) -> None:
    """Recheck provenance binding, all marginals, and a numerical certificate.

    Verification evaluates the stored dual weights; it does not re-optimize.
    Never trust a stored 'converged' flag or gap supplied by an export.
    """
    try:
        if report["version"] != 1 or report["model"] != MODEL or report["graph_sha256"] != graph_digest(kb):
            raise ValueError("stale model or graph")
        priors = atom_priors(kb)
        if report["priors"] != priors or set(report["probabilities"]) != set(priors):
            raise ValueError("incomplete atom coverage")
        groups = components(kb)
        if len(report["components"]) != len(groups):
            raise ValueError("incomplete component coverage")
        for (ids, clauses), stored in zip(groups, report["components"]):
            if stored["atom_ids"] != ids or stored["clause_ids"] != [a["id"] for a in clauses]:
                raise ValueError("incorrect component membership")
            program = ExactMarginals(len(ids), features_for(ids, clauses, priors))
            weights = np.array(stored["weights"], dtype=float)
            if weights.shape != (len(program.features),) or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
                raise ValueError("invalid dual weights")
            actual = certificate(program, weights)
            if actual["duality_gap"] > GAP_TOLERANCE:
                raise ValueError("unconverged inference")
            expected = {
                "probabilities": dict(zip(ids, map(float, actual["atoms"]))),
                "clause_probabilities": dict(zip((a["id"] for a in clauses), map(float, actual["means"][:len(clauses)]))),
            }
            for field, values in expected.items():
                if set(stored[field]) != set(values):
                    raise ValueError("incomplete marginal coverage")
                for pid, p in values.items():
                    number = stored[field][pid]
                    if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1 or abs(number-p) > 1e-9:
                        raise ValueError("invalid marginal probability")
                    if field == "probabilities" and report["probabilities"][pid] != number:
                        raise ValueError("inconsistent marginal probability")
            for field in ("duality_gap", "entropy", "objective"):
                if not math.isfinite(stored[field]) or abs(stored[field] - actual[field]) > 1e-9:
                    raise ValueError("invalid numerical certificate")
            if stored["method"] != "exact-variable-elimination" or stored["elimination_width"] != program.width:
                raise ValueError("incorrect inference method")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InferenceError("Invalid, stale or unconverged probability export") from exc
