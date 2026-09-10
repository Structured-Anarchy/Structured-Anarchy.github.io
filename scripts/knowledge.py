#!/usr/bin/env python3
"""Author, validate, and encrypt the private shared knowledge base."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tomli_w
from cryptography.exceptions import InvalidTag

from sitegen.knowledge import DEFAULT_KNOWLEDGE, KnowledgeError, digest, empty_knowledge, load_knowledge, local_data_path, make_origin, validate_local
from sitegen.vault import decrypt_archive, pack, unpack, validate_envelope
from sitegen.inference import infer, validate_inference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create an empty data/knowledge/knowledge.toml without overwriting")
    register = commands.add_parser("register-source", help="register a refined transcript and its current byte hash")
    register.add_argument("file_name")
    register.add_argument("--id", required=True)
    register.add_argument("--label", required=True)
    cite = commands.add_parser("cite", help="print a TOML origin pointer; never count characters manually")
    cite.add_argument("file_name")
    cite.add_argument("--start", type=int)
    cite.add_argument("--stop", type=int)
    cite.add_argument("--quote-file", type=Path, help="file containing the exact excerpt, including any trailing newline")
    spans = commands.add_parser("spans", help="print every codepoint range for a symbol surface in a proposition")
    spans.add_argument("proposition_id")
    spans.add_argument("surface")
    commands.add_parser("validate", help="check schema, graph integrity, and every source pointer")
    commands.add_parser("infer", help="compute and validate private component probabilities without changing the archive")
    commands.add_parser("check-envelope", help="validate ciphertext packaging without a passkey")
    for name in ("pack", "unpack", "verify-encrypted"):
        sub = commands.add_parser(name)
        secret = sub.add_mutually_exclusive_group()
        secret.add_argument("--passkey-file", type=Path)
        secret.add_argument("--passkey-env", help="environment variable name, never the passkey itself")
    args = parser.parse_args()
    root = args.root.resolve()
    kb_path = root / DEFAULT_KNOWLEDGE
    try:
        if args.command == "init":
            kb_path.parent.mkdir(parents=True, exist_ok=True)
            with kb_path.open("xb") as handle:
                handle.write(tomli_w.dumps(empty_knowledge()).encode("utf-8"))
            print("Created empty private knowledge base.")
        elif args.command == "register-source":
            if not args.file_name.startswith("data/refined-transcripts/") or not args.file_name.endswith(".txt"):
                raise ValueError("register only refined .txt transcripts")
            kb = load_knowledge(kb_path)
            if any(s["id"] == args.id or s["file_name"] == args.file_name for s in kb["sources"]):
                raise ValueError("source already registered; do not refresh its hash to bypass stale pointers")
            raw = local_data_path(root, args.file_name).read_bytes()
            raw.decode("utf-8")
            kb["sources"].append(dict(id=args.id, file_name=args.file_name, label=args.label, sha256=digest(raw)))
            kb_path.write_text(tomli_w.dumps(kb), encoding="utf-8")
            print("Registered source; add its session and occurrences during extraction.")
        elif args.command == "spans":
            kb = load_knowledge(kb_path)
            matches = [p for p in kb["propositions"] if p["id"] == args.proposition_id]
            if len(matches) != 1 or not args.surface:
                raise ValueError("specify an existing unique proposition id and a nonempty surface")
            text = matches[0]["text"]
            start = text.find(args.surface)
            if start < 0:
                raise ValueError("surface does not occur in this proposition")
            while start >= 0:
                print(f"{{ start_char = {start}, stop_char = {start + len(args.surface)} }}")
                start = text.find(args.surface, start + len(args.surface))
        elif args.command == "cite":
            raw = local_data_path(root, args.file_name).read_bytes()
            start, stop = args.start, args.stop
            if args.quote_file is not None:
                if start is not None or stop is not None:
                    raise ValueError("use either --quote-file or --start/--stop")
                quote = args.quote_file.read_bytes().decode("utf-8")
                text = raw.decode("utf-8")
                start = text.find(quote)
                if not quote or start < 0 or text.find(quote, start + 1) >= 0:
                    raise ValueError("quote must match exactly once; extend it or use explicit offsets")
                stop = start + len(quote)
            if start is None or stop is None:
                raise ValueError("provide --quote-file or both --start and --stop")
            pointer = make_origin(args.file_name, raw, start, stop)
            print("{ " + ", ".join(f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in pointer.items()) + " }")
        elif args.command == "validate":
            kb = validate_local(root)
            print(f"Validated {len(kb['propositions'])} propositions and {len(kb['arguments'])} arguments, including every origin pointer.")
        elif args.command == "infer":
            kb = validate_local(root)
            report = infer(kb)
            validate_inference(kb, report)
            target = local_data_path(root, "data/knowledge/inference.json")
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(f"Computed {len(report['probabilities'])} probabilities across {len(report['components'])} exact components; report saved privately.")
        elif args.command == "check-envelope":
            validate_envelope(root / "encrypted")
            print("Encrypted envelope and asset hashes passed. Plaintext provenance requires verify-encrypted.")
        else:
            if args.passkey_file:
                passkey = args.passkey_file.read_text(encoding="utf-8").rstrip("\r\n")
            elif args.passkey_env:
                passkey = os.environ.get(args.passkey_env, "")
                if not passkey:
                    raise ValueError("passkey environment variable is missing or empty")
            else:
                passkey = getpass.getpass("Content passkey: ")
            if args.command == "pack":
                summary = pack(root, root / "encrypted", passkey)
                print("Encrypted export created: " + ", ".join(f"{n} {k}" for k, n in summary.items()))
            elif args.command == "unpack":
                # The archive belongs to this checkout even when --root is a fresh destination.
                count = unpack(ROOT / "encrypted", root, passkey)
                print(f"Restored {count} private files into data/.")
            else:
                kb, files = decrypt_archive(root / "encrypted", passkey)
                print(f"Decrypted and validated {len(files)} files and {len(kb['propositions'])} propositions.")
    except InvalidTag:
        print("error: incorrect passkey or damaged encrypted content", file=sys.stderr)
        return 1
    except (KnowledgeError, OSError, ValueError, KeyError, TypeError) as exc:
        if args.command == "verify-encrypted":
            print(f"error: private validation failed ({type(exc).__name__}); run validate locally for details", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
