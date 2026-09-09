"""Validate the shared argument graph and exact, versioned transcript provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tomllib
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

from .sessions import with_session_metadata

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "knowledge.schema.json"
COLLECTIONS = ("sources", "sessions", "symbols", "meanings", "propositions", "arguments", "occurrences", "questions")
DEFAULT_KNOWLEDGE = "data/knowledge/knowledge.toml"


class KnowledgeError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def empty_knowledge() -> dict[str, Any]:
    return {"schema_version": 1, **{name: [] for name in COLLECTIONS}}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def local_data_path(root: Path, name: str) -> Path:
    """Only relative, canonical data paths; never follow links outside data/."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name or len(path.parts) < 2 or path.parts[0] != "data":
        raise ValueError("expected a canonical relative path inside data/")
    target = (root / name).resolve()
    if (root / "data").is_symlink():
        raise ValueError("data/ itself must not be a symlink")
    if not target.is_relative_to((root / "data").resolve()):
        raise ValueError("path escapes data/")
    return target


def make_origin(name: str, raw: bytes, start: int, stop: int) -> dict[str, Any]:
    # Decode bytes directly: universal-newline conversion would move character offsets.
    text = raw.decode("utf-8")
    if not 0 <= start < stop <= len(text):
        raise ValueError("expected 0 <= start_char < stop_char <= character count")
    passage = text[start:stop]
    return dict(file_name=name, start_char=start, stop_char=stop,
                first_6_chars=passage[:6], last_6_chars=passage[-6:])


def load_knowledge(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise KnowledgeError([f"cannot read knowledge TOML: {exc}"]) from exc


def validate_knowledge(kb: dict[str, Any], read_source: Callable[[str], bytes]) -> None:
    """Check schema, references, logical shape, and every provenance pointer.

    read_source abstracts local files versus decrypted archive entries. Validation
    never claims that an extract is a faithful interpretation of a passage.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [f"{'.'.join(map(str, e.absolute_path)) or 'knowledge'}: {e.message}"
              for e in validator.iter_errors(kb)]
    if errors:
        raise KnowledgeError(errors)

    indexes: dict[str, dict[str, Any]] = {}
    all_ids: set[str] = set()
    for collection in COLLECTIONS:
        indexes[collection] = {}
        for item in kb[collection]:
            if item["id"] in all_ids:
                errors.append(f"duplicate id: {item['id']}")
            all_ids.add(item["id"])
            indexes[collection][item["id"]] = item

    def reference(collection: str, value: str, where: str) -> Any:
        item = indexes[collection].get(value)
        if item is None:
            errors.append(f"{where}: unknown {collection} id {value}")
        return item

    texts: dict[str, str] = {}
    source_names: set[str] = set()
    for source in kb["sources"]:
        name = source["file_name"]
        if not name.startswith("data/refined-transcripts/") or not name.endswith(".txt"):
            errors.append(f"{source['id']}: provenance must reference a refined .txt transcript")
        if name in source_names:
            errors.append(f"duplicate source file: {name}")
        source_names.add(name)
        try:
            local_data_path(Path("/"), name)
            raw = read_source(name)
            if digest(raw) != source["sha256"]:
                errors.append(f"{source['id']}: source SHA-256 mismatch; restore the version or re-extract affected pointers")
            texts[name] = raw.decode("utf-8")
        except (OSError, KeyError, ValueError) as exc:
            errors.append(f"{source['id']}: unreadable source ({type(exc).__name__})")

    # Walk all origins, including bindings and each literal occurrence, so future
    # provenance-bearing records cannot accidentally bypass the range check.
    def walk(value: Any, where: str) -> None:
        if isinstance(value, dict):
            if "file_name" in value and "start_char" in value:
                text = texts.get(value["file_name"])
                if text is None:
                    errors.append(f"{where}: unregistered or unreadable source")
                else:
                    start, stop = value["start_char"], value["stop_char"]
                    if not 0 <= start < stop <= len(text):
                        errors.append(f"{where}: invalid character range")
                    else:
                        passage = text[start:stop]
                        if passage[:6] != value["first_6_chars"] or passage[-6:] != value["last_6_chars"]:
                            errors.append(f"{where}: first/last six characters do not match")
            for key, child in value.items():
                walk(child, f"{where}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{where}[{i}]")

    walk(kb, "knowledge")
    for session in kb["sessions"]:
        for source_id in session["source_ids"]:
            reference("sources", source_id, session["id"])

    for meaning in kb["meanings"]:
        reference("symbols", meaning["symbol_id"], meaning["id"])
    for symbol in kb["symbols"]:
        defaults = [m for m in kb["meanings"] if m["symbol_id"] == symbol["id"] and m["kind"] == "normative"]
        if len(defaults) != 1:
            errors.append(f"{symbol['id']}: requires exactly one Normative (undeclared) meaning")

    signatures: set[str] = set()
    for proposition in kb["propositions"]:
        induced = proposition.get("evidence_status") == "induced"
        if "induction" in proposition:
            for aid in proposition["induction"]["argument_ids"]:
                argument = reference("arguments", aid, proposition["id"])
                if argument and not any(l["proposition_id"] == proposition["id"] for l in argument["premises"]):
                    errors.append(f"{proposition['id']}: induction must identify a clause using this premise")
        spans: list[tuple[int, int]] = []
        for binding in proposition["bindings"]:
            where = proposition["id"]
            if not induced and not binding["origins"]:
                errors.append(f"{where}: sourced symbol binding requires origins")
            start, stop = binding["start_char"], binding["stop_char"]
            if not 0 <= start < stop <= len(proposition["text"]):
                errors.append(f"{where}: invalid symbol character range")
            if any(start < end and stop > begin for begin, end in spans):
                errors.append(f"{where}: overlapping symbol ranges")
            spans.append((start, stop))
            symbol = reference("symbols", binding["symbol_id"], where)
            if symbol and proposition["text"][start:stop].casefold() not in {s.casefold() for s in [symbol["label"], *symbol["aliases"]]}:
                errors.append(f"{where}: symbol surface text is absent from its label/aliases")
            if set(binding["meaning_ids"]) & set(binding["excluded_meaning_ids"]):
                errors.append(f"{where}: a meaning cannot be both selected and excluded")
            if binding["selection"] == "specified" and len(binding["meaning_ids"]) != 1:
                errors.append(f"{where}: multiple meanings require ambiguous or collective selection")
            for meaning_id in binding["meaning_ids"] + binding["excluded_meaning_ids"]:
                meaning = reference("meanings", meaning_id, where)
                if meaning and meaning["symbol_id"] != binding["symbol_id"]:
                    errors.append(f"{where}: meaning belongs to a different symbol")
        signature = json.dumps([proposition["text"].casefold(), proposition["scope"].casefold(), proposition["kind"], sorted(
            [(b["start_char"], b["stop_char"], b["symbol_id"], sorted(b["meaning_ids"]), b["selection"]) for b in proposition["bindings"]])])
        if signature in signatures:
            errors.append(f"{proposition['id']}: duplicate proposition and interpretation; reuse its existing id")
        signatures.add(signature)

    rule_signatures: set[tuple] = set()
    for argument in kb["arguments"]:
        literals = [*argument["premises"], argument["conclusion"]]
        for literal in literals:
            proposition = reference("propositions", literal["proposition_id"], argument["id"])
            if proposition and proposition.get("evidence_status") != "induced" and not literal["origins"]:
                errors.append(f"{argument['id']}: sourced literal requires origins")
        sourced_premises = [p for p in argument["premises"] if p["origins"] and
                           indexes["propositions"].get(p["proposition_id"], {}).get("evidence_status") != "induced"]
        if not sourced_premises:
            errors.append(f"{argument['id']}: antecedent requires at least one source-substantiated atom")
        if any(indexes["propositions"].get(p["proposition_id"], {}).get("evidence_status") == "induced"
               for p in argument["premises"]) and argument["explicitness"] != "reconstructed":
            errors.append(f"{argument['id']}: a clause with induced premises must be reconstructed")
        premises = [(p["proposition_id"], p["negated"]) for p in argument["premises"]]
        conclusion = argument["conclusion"]
        if len(set(premises)) != len(premises):
            errors.append(f"{argument['id']}: duplicate premise literal")
        if any((p, not n) in premises for p, n in premises):
            errors.append(f"{argument['id']}: contradictory antecedent is vacuously true")
        if (conclusion["proposition_id"], conclusion["negated"]) in premises:
            errors.append(f"{argument['id']}: tautological self-support")
        # In disjunctive form each negative premise becomes a positive literal.
        positive_count = sum(p["negated"] for p in argument["premises"]) + int(not conclusion["negated"])
        if positive_count > 1:
            errors.append(f"{argument['id']}: not a Horn clause (more than one positive literal in disjunctive form)")
        signature = (tuple(sorted(premises)), conclusion["proposition_id"], conclusion["negated"])
        if signature in rule_signatures:
            errors.append(f"{argument['id']}: duplicate argument; merge provenance and occurrences")
        rule_signatures.add(signature)

    observed: set[tuple[str, str]] = set()
    for occurrence in kb["occurrences"]:
        session = reference("sessions", occurrence["session_id"], occurrence["id"])
        target_type = occurrence["target_type"]
        target = reference({"proposition": "propositions", "argument": "arguments", "meaning": "meanings"}[target_type], occurrence["target_id"], occurrence["id"])
        if target_type == "proposition" and target and target.get("evidence_status") == "induced" and occurrence["stance"] in {"asserted", "withdrawn"}:
            errors.append(f"{occurrence['id']}: an unsubstantiated induced atom cannot have an asserted or withdrawn source occurrence")
        observed.add((target_type, occurrence["target_id"]))
        if session:
            allowed = {indexes["sources"][sid]["file_name"] for sid in session["source_ids"] if sid in indexes["sources"]}
            if any(p["file_name"] not in allowed for p in occurrence["origins"]):
                errors.append(f"{occurrence['id']}: occurrence evidence is outside its session")
    for collection, target_type in [("propositions", "proposition"), ("arguments", "argument"), ("meanings", "meaning")]:
        for item in kb[collection]:
            if item.get("kind") == "normative" and collection == "meanings":
                continue
            if collection == "propositions" and item.get("evidence_status") == "induced":
                continue  # Reconstruction context is not invented session testimony.
            if (target_type, item["id"]) not in observed:
                errors.append(f"{item['id']}: requires at least one session occurrence")
    for question in kb["questions"]:
        if "session_id" in question:
            session = reference("sessions", question["session_id"], question["id"])
            if session:
                allowed = {indexes["sources"][sid]["file_name"] for sid in session["source_ids"] if sid in indexes["sources"]}
                if any(origin["file_name"] not in allowed for origin in question["origins"]):
                    errors.append(f"{question['id']}: question evidence is outside its session")
        for pid in question["proposition_ids"]:
            reference("propositions", pid, question["id"])
        for sid in question["symbol_ids"]:
            reference("symbols", sid, question["id"])
    if errors:
        raise KnowledgeError(errors)


def validate_local(root: Path, path: Path | None = None) -> dict[str, Any]:
    kb = load_knowledge(path or root / DEFAULT_KNOWLEDGE)
    kb = with_session_metadata(kb, lambda name: local_data_path(root, name).read_bytes())
    validate_knowledge(kb, lambda name: local_data_path(root, name).read_bytes())
    return kb
