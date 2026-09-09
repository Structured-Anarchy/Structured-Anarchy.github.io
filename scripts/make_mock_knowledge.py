#!/usr/bin/env python3
"""Create an explicitly fictional two-session graph in a fresh test workspace."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tomli_w

from sitegen.knowledge import DEFAULT_KNOWLEDGE, digest, empty_knowledge, make_origin, validate_knowledge

MOCK_ONE = """🌿 Fictional session one — this is test material, not a group transcript.
[00:00] The garden should stay open.
[00:10] The garden is quiet.
[00:20] By quiet I mean little traffic noise.
[00:25] Birdsong is permitted within that meaning of quiet.
[00:30] Quiet can also mean a place that feels calm. I intend both meanings here.
[00:40] Quiet could mean absolutely silent, but I exclude that meaning here.
[00:50] Quiet places should stay open. Because the garden is quiet and quiet places should stay open, the garden should stay open.
[01:00] The garden is costly. For every costly place, the claim that it should stay open is false. Therefore it is false that the garden should stay open.
[01:10] The garden should stay open only if it is quiet. Given that the garden should stay open, the garden is quiet.
"""
MOCK_TWO = """Fictional session two — this is test material, not a group transcript.
[00:00] The garden should stay open. I am using quiet in the same two meanings as before.
[00:10] The library should stay open. The library is quiet. Quiet places should stay open. Those last two claims support keeping the library open.
[00:20] What do we mean by costly?
"""


def mock_knowledge() -> tuple[dict, dict[str, bytes]]:
    kb = empty_knowledge()
    files = {"data/refined-transcripts/mock-one.txt": MOCK_ONE.encode(), "data/refined-transcripts/mock-two.txt": MOCK_TWO.encode()}

    def cite(text: str, session: str = "one") -> dict:
        name = f"data/refined-transcripts/mock-{session}.txt"
        source = files[name].decode()
        start = source.index(text)
        return make_origin(name, files[name], start, start + len(text))

    def line(timestamp: str, session: str = "one") -> dict:
        source = files[f"data/refined-transcripts/mock-{session}.txt"].decode()
        return cite(next(row for row in source.splitlines() if row.startswith(timestamp)), session)

    for number, (name, raw) in zip(("one", "two"), files.items()):
        kb["sources"].append(dict(id=f"source-{number}", file_name=name, sha256=digest(raw), label=f"Fictional session {number}"))
        kb["sessions"].append(dict(id=f"session-{number}", title=f"Fictional session {number}", source_ids=[f"source-{number}"]))

    aliases = {"garden": [], "library": [], "quiet": ["Quiet"], "place": ["places"], "open": ["stay open", "staying open"], "costly": ["Costly"], "close": []}
    for label, forms in aliases.items():
        kb["symbols"].append(dict(id=f"symbol-{label}", label=label, aliases=forms))
        kb["meanings"].append(dict(id=f"meaning-{label}-normative", symbol_id=f"symbol-{label}", kind="normative", definition="Normative (undeclared)", origins=[]))
    definitions = [
        ("low-noise", "Little traffic noise; birdsong is permitted.", [line("[00:20]"), line("[00:25]")]),
        ("calm", "A place that feels calm.", [line("[00:30]")]),
        ("silent", "An absence of all sound.", [line("[00:40]")]),
    ]
    for suffix, definition, origins in definitions:
        mid = f"meaning-quiet-{suffix}"
        kb["meanings"].append(dict(id=mid, symbol_id="symbol-quiet", kind="defined", definition=definition, origins=origins))
        kb["occurrences"].append(dict(id=f"occurrence-{suffix}", session_id="session-one", target_type="meaning", target_id=mid, stance="hypothetical" if suffix == "silent" else "asserted", origins=origins))

    specs = [
        ("garden-open", "The garden should stay open.", "normative", True, "one", ["garden", "stay open"]),
        ("garden-quiet", "The garden is quiet.", "empirical", False, "one", ["garden", "quiet"]),
        ("quiet-open", "Quiet places should stay open.", "normative", False, "one", ["Quiet", "places", "stay open"]),
        ("garden-costly", "The garden is costly.", "empirical", False, "one", ["garden", "costly"]),
        ("costly-close", "For every costly place, the claim that it should stay open is false.", "normative", False, "one", ["costly", "place", "stay open"]),
        ("library-open", "The library should stay open.", "normative", True, "two", ["library", "stay open"]),
        ("library-quiet", "The library is quiet.", "empirical", False, "two", ["library", "quiet"]),
        ("open-only-quiet", "The garden should stay open only if it is quiet.", "normative", False, "one", ["garden", "stay open", "quiet"]),
    ]
    for pid, text, kind, thesis, session, surfaces in specs:
        origins = [cite(text, session)]
        bindings = []
        for surface in surfaces:
            label = next(label for label, forms in aliases.items() if surface == label or surface in forms)
            selected = [f"meaning-{label}-normative"]
            excluded = []
            evidence = deepcopy(origins)
            selection = "specified"
            if label == "quiet":
                selected = ["meaning-quiet-low-noise", "meaning-quiet-calm"]
                excluded = ["meaning-quiet-silent"]
                selection = "collective"
                evidence += [line("[00:30]"), line("[00:40]")]
                if session == "two":
                    evidence.append(line("[00:00]", "two"))
            start = text.index(surface)
            bindings.append(dict(start_char=start, stop_char=start + len(surface), symbol_id=f"symbol-{label}", meaning_ids=selected, excluded_meaning_ids=excluded, selection=selection, origins=evidence))
        kb["propositions"].append(dict(id=pid, text=text, scope="The shared spaces in these fictional sessions.", kind=kind, thesis=thesis, topics=["Shared spaces"], origins=origins, bindings=bindings))
        kb["occurrences"].append(dict(id=f"occurrence-{pid}", session_id=f"session-{session}", target_type="proposition", target_id=pid, stance="asserted", origins=deepcopy(origins)))
    for pid in ("garden-open", "quiet-open"):
        proposition = next(p for p in kb["propositions"] if p["id"] == pid)
        origin = cite(proposition["text"], "two")
        proposition["origins"].append(origin)
        kb["occurrences"].append(dict(id=f"occurrence-{pid}-again", session_id="session-two", target_type="proposition", target_id=pid, stance="asserted", origins=[origin]))
    kb["occurrences"].append(dict(id="occurrence-garden-open-rejected", session_id="session-one",
        target_type="proposition", target_id="garden-open", stance="rejected", origins=[line("[01:00]")]))

    rules = [
        ("argument-garden-support", ["garden-quiet", "quiet-open"], "garden-open", False, "[00:50]", "one", "The two premises jointly support keeping the garden open."),
        ("argument-garden-refute", ["garden-costly", "costly-close"], "garden-open", True, "[01:00]", "one", "Costliness and a policy denying the opening obligation jointly negate that obligation, rather than merely propose a contrary obligation."),
        ("argument-cycle", ["garden-open", "open-only-quiet"], "garden-quiet", False, "[01:10]", "one", "The opening obligation and the stated necessary condition jointly entail quietness. The resulting cycle is not independent evidence."),
        ("argument-library-support", ["library-quiet", "quiet-open"], "library-open", False, "[00:10]", "two", "The quietness argument is reused for the library."),
    ]
    for rid, premises, conclusion, negated, timestamp, session, explanation in rules:
        origins = [line(timestamp, session)]
        literal = lambda pid, sign=False: dict(proposition_id=pid, negated=sign, origins=deepcopy(origins))
        kb["arguments"].append(dict(id=rid, premises=[literal(pid) for pid in premises], conclusion=literal(conclusion, negated), explicitness="explicit", explanation=explanation, origins=origins))
        kb["occurrences"].append(dict(id=f"occurrence-{rid}", session_id=f"session-{session}", target_type="argument", target_id=rid, stance="asserted", origins=deepcopy(origins)))
    kb["questions"].append(dict(id="question-costly", text="What do we mean by costly?", proposition_ids=["garden-costly"], symbol_ids=["symbol-costly"], origins=[line("[00:20]", "two")]))
    validate_knowledge(kb, files.__getitem__)
    return kb, files


def write_mock(root: Path) -> dict:
    if (root / "data").exists():
        raise ValueError("mock root must not already contain data/; use a fresh temporary directory")
    kb, files = mock_knowledge()
    files[DEFAULT_KNOWLEDGE] = tomli_w.dumps(kb).encode()
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return kb


def add_induced_mock(kb: dict, files: dict[str, bytes]) -> None:
    """Add a fictional incomplete reason and its expressly unspoken policy."""
    name = "data/refined-transcripts/mock-two.txt"
    extra = "[00:30] This library hosts neighbourhood study groups. That is why the library should stay open.\r\n"
    start = len(files[name].decode())
    files[name] += extra.encode()
    source = next(s for s in kb["sources"] if s["file_name"] == name)
    source["sha256"] = digest(files[name])
    context = make_origin(name, files[name], start, start + len(extra))
    fact_text = "This library hosts neighbourhood study groups."
    fact_origin = make_origin(name, files[name], start + 8, start + 8 + len(fact_text))
    policy_text = "Libraries hosting neighbourhood study groups should stay open."
    aid = "argument-library-study"
    for label, aliases in [("hosts", ["hosting"]), ("neighbourhood study groups", [])]:
        suffix = label.replace(" ", "-")
        kb["symbols"].append(dict(id="symbol-" + suffix, label=label, aliases=aliases))
        kb["meanings"].append(dict(id="meaning-" + suffix + "-normative", symbol_id="symbol-" + suffix,
            kind="normative", definition="Normative (undeclared)", origins=[]))
    next(s for s in kb["symbols"] if s["id"] == "symbol-library")["aliases"].append("Libraries")
    for pid, text, kind, origins in [
        ("library-study", fact_text, "empirical", [fact_origin]),
        ("study-open", policy_text, "normative", []),
    ]:
        bindings = []
        for surface, sid in ([
            ("library", "symbol-library"), ("hosts", "symbol-hosts"),
            ("neighbourhood study groups", "symbol-neighbourhood-study-groups")
        ] if origins else [
            ("Libraries", "symbol-library"), ("hosting", "symbol-hosts"),
            ("neighbourhood study groups", "symbol-neighbourhood-study-groups"), ("stay open", "symbol-open")
        ]):
            at = text.index(surface)
            bindings.append(dict(start_char=at, stop_char=at + len(surface), symbol_id=sid,
                                 meaning_ids=[sid.replace("symbol-", "meaning-") + "-normative"],
                                 excluded_meaning_ids=[], selection="specified", origins=deepcopy(origins)))
        proposition = dict(id=pid, text=text, scope="These fictional neighbourhood libraries.", kind=kind,
                           thesis=False, topics=["Shared spaces"], origins=origins, bindings=bindings)
        if not origins:
            proposition.update(evidence_status="induced", induction=dict(
                rationale="Hosting study groups does not establish an opening obligation without a normative policy connecting that use to continued opening.",
                argument_ids=[aid], context_origins=[context]))
        else:
            kb["occurrences"].append(dict(id="occurrence-library-study", session_id="session-two",
                target_type="proposition", target_id=pid, stance="asserted", origins=deepcopy(origins)))
        kb["propositions"].append(proposition)
    kb["arguments"].append(dict(id=aid, premises=[
        dict(proposition_id="library-study", negated=False, origins=[fact_origin]),
        dict(proposition_id="study-open", negated=False, origins=[])],
        conclusion=dict(proposition_id="library-open", negated=False, origins=[context]),
        explicitness="reconstructed", explanation="The expressed study-group reason needs an unspoken normative policy.", origins=[context]))
    kb["occurrences"].append(dict(id="occurrence-library-study-argument", session_id="session-two",
        target_type="argument", target_id=aid, stance="asserted", origins=[context]))
    validate_knowledge(kb, files.__getitem__)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    write_mock(args.root)
    print("Created fictional transcripts and a validated example knowledge base.")
