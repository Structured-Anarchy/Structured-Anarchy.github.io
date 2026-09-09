#!/usr/bin/env python3
"""Reject tracked data, exposed passkeys, and readable private content in public files.

PRs can check paths and ciphertext without a secret. Trusted main builds can
decrypt the archive in memory to validate all provenance and check for leaks.
This is a regression guard, not a proof that arbitrary paraphrases are private.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sitegen.vault import decrypt_archive, validate_envelope


def private_fragments(files: dict[str, bytes], kb: dict | None = None) -> set[bytes]:
    fragments: set[bytes] = set()
    for raw in files.values():
        # Long windows detect accidental copying without matching common short words.
        for line in raw.splitlines():
            if len(line) >= 100:
                fragments.update(line[start:start + 100] for start in range(0, len(line) - 99, 50))
    if kb:
        for collection, field in [("propositions", "text"), ("meanings", "definition"), ("arguments", "explanation")]:
            for item in kb.get(collection, []):
                value = item.get(field, "").encode("utf-8")
                if len(value) >= 25 and item.get("kind") != "normative":
                    fragments.add(value)
                elif collection == "propositions" and len(value) >= 25:
                    fragments.add(value)
    return fragments


def scan_paths(paths: list[Path], fragments: set[bytes], passkey: str = "") -> list[Path]:
    needles = fragments | ({passkey.encode("utf-8")} if passkey else set())
    failures = []
    for path in paths:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if any(needle in raw for needle in needles):
            failures.append(path)
    return failures


def check(root: Path, output: Path | None = None, passkey: str = "") -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    forbidden = [name for name in tracked if name.startswith(("data/", "dist/", "_site/", "node_modules/"))]
    if forbidden:
        raise ValueError("private data or generated directories are tracked; remove them from the index")
    if subprocess.check_output(["git", "check-ignore", "data/probe.txt"], cwd=root).strip() != b"data/probe.txt":
        raise ValueError("data/* must be ignored")
    candidates = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).decode().split("\0")
    paths = [root / name for name in candidates if name]
    if output:
        paths.extend(path for path in output.rglob("*") if path.is_file())
        if (output / "data").exists():
            raise ValueError("build output contains a readable data directory")
    files: dict[str, bytes] = {}
    kb = None
    if (root / "encrypted").exists():
        validate_envelope(root / "encrypted")
    if passkey:
        kb, files = decrypt_archive(root / "encrypted", passkey)
    else:
        for folder in ("transcripts", "refined-transcripts", "knowledge"):
            for path in (root / "data" / folder).rglob("*"):
                if path.is_file() and path.suffix in {".txt", ".toml", ".md"}:
                    files[path.relative_to(root).as_posix()] = path.read_bytes()
        authoring = files.get("data/knowledge/knowledge.toml")
        if authoring:
            kb = tomllib.loads(authoring.decode("utf-8"))
    local_secret = root / "data/.passkey"
    needle_passkey = passkey or (local_secret.read_text(encoding="utf-8").rstrip("\r\n") if local_secret.exists() else "")
    leaked = scan_paths(paths, private_fragments(files, kb), needle_passkey)
    if leaked:
        raise ValueError("readable private content detected in public file(s): " + ", ".join(str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in leaked))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--passkey-env", help="name of a required environment variable")
    args = parser.parse_args()
    passkey = os.environ.get(args.passkey_env, "") if args.passkey_env else ""
    if args.passkey_env and not passkey:
        print("error: configure the CONTENT_PASSKEY repository secret for private validation", file=sys.stderr)
        return 1
    try:
        check(ROOT, args.output, passkey)
    except Exception as exc:
        # Public CI logs must not serialize exceptions containing decrypted records.
        if args.passkey_env:
            print(f"error: private-content checks failed ({type(exc).__name__}); run the validator locally for details", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Private-content checks passed" + (", including decrypted provenance." if passkey else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
