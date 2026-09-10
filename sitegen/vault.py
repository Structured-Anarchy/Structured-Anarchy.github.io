"""Authenticated, browser-compatible storage for private knowledge and transcripts.

Only the manifest and opaque ciphertext assets leave data/. All files in an
export share a PBKDF2-derived key and have independent random GCM nonces. Their
asset names are authenticated to prevent swapping ciphertext between resources.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import shutil
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .knowledge import DEFAULT_KNOWLEDGE, digest, local_data_path, validate_knowledge, validate_local
from .sessions import with_session_metadata
from .inference import infer, validate_inference

ITERATIONS = 600_000
ASSET_RE = re.compile(r"^[a-f0-9]{32}\.bin$")
MANIFEST_KEYS = {"version", "cipher", "kdf", "iterations", "salt", "catalog", "assets"}


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def derive_key(passkey: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    if not passkey:
        raise ValueError("passkey must not be empty")
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(passkey.encode("utf-8"))


def aad(name: str) -> bytes:
    return f"structured-anarchy:v1:{name}".encode("ascii")


def seal(key: bytes, name: str, raw: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, raw, aad(name))


def unseal(key: bytes, name: str, raw: bytes) -> bytes:
    if len(raw) < 28:
        raise ValueError("truncated encrypted resource")
    return AESGCM(key).decrypt(raw[:12], raw[12:], aad(name))


def validate_envelope(directory: Path) -> dict[str, Any]:
    """Public checks need no passkey and run on untrusted PRs as well as builds."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("invalid encrypted manifest fields")
    if manifest["version"] != 1 or manifest["cipher"] != "AES-256-GCM" or manifest["kdf"] != "PBKDF2-SHA256":
        raise ValueError("unsupported encrypted manifest format")
    if type(manifest["iterations"]) is not int or not ITERATIONS <= manifest["iterations"] <= 2_000_000:
        raise ValueError("invalid PBKDF2 work factor")
    if not isinstance(manifest["salt"], str) or len(base64.b64decode(manifest["salt"], validate=True)) != 16:
        raise ValueError("invalid PBKDF2 salt")
    assets = manifest["assets"]
    if not isinstance(assets, dict) or not assets or manifest["catalog"] not in assets:
        raise ValueError("missing encrypted catalog")
    for name, checksum in assets.items():
        if not ASSET_RE.fullmatch(name) or not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("invalid encrypted asset entry")
        asset = directory / name
        if asset.is_symlink() or not asset.is_file():
            raise ValueError(f"missing or linked encrypted asset: {name}")
        raw = asset.read_bytes()
        if len(raw) < 28 or digest(raw) != checksum:
            raise ValueError(f"encrypted asset integrity check failed: {name}")
    expected = {"manifest.json", *assets}
    if {p.name for p in directory.iterdir()} != expected:
        raise ValueError("encrypted/ contains unexpected files; only manifest and ciphertext are permitted")
    return manifest


def pack(root: Path, output: Path, passkey: str) -> dict[str, int]:
    kb = validate_local(root)
    # Compute before touching the existing export. Failure must not publish a
    # partial graph, stale probabilities, or a sampled approximation.
    probabilities = infer(kb)
    validate_inference(kb, probabilities)
    salt = os.urandom(16)
    key = derive_key(passkey, salt)
    assets: dict[str, bytes] = {}

    def add(raw: bytes) -> dict[str, str]:
        name = secrets.token_hex(16) + ".bin"
        assets[name] = seal(key, name, raw)
        return {"asset": name, "sha256": digest(raw)}

    files = []
    # Audio stays local. Preserve both original and refined text byte-for-byte.
    names = {p.relative_to(root).as_posix() for folder in ("transcripts", "refined-transcripts")
             for p in (root / "data" / folder).rglob("*.txt")}
    names.update(source["file_name"] for source in kb["sources"])
    names.add(DEFAULT_KNOWLEDGE)
    names.update(session["metadata_file"] for session in kb["sessions"] if "metadata_file" in session)
    names.update(p.relative_to(root).as_posix() for p in (root / "data/knowledge/reviews").rglob("*.md"))
    for name in sorted(names):
        raw = local_data_path(root, name).read_bytes()
        raw.decode("utf-8")
        files.append({"file_name": name, **add(raw)})
    graph = add(json_bytes(kb))
    inference = add(json_bytes(probabilities))
    catalog = add(json_bytes({"version": 1, "graph": graph, "inference": inference, "files": files}))
    manifest = {
        "version": 1, "cipher": "AES-256-GCM", "kdf": "PBKDF2-SHA256",
        "iterations": ITERATIONS, "salt": base64.b64encode(salt).decode("ascii"),
        "catalog": catalog["asset"], "assets": {name: digest(raw) for name, raw in assets.items()},
    }
    # Refuse to repurpose an unrelated directory, then publish the manifest last.
    if output.exists() and any(output.iterdir()):
        validate_envelope(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in assets.items():
        (output / name).write_bytes(raw)
    temporary = output / ".manifest.tmp"
    temporary.write_bytes(json_bytes(manifest))
    temporary.replace(output / "manifest.json")
    for path in output.glob("*.bin"):
        if path.name not in assets:
            path.unlink()
    validate_envelope(output)
    return {"transcripts": sum(name.endswith(".txt") for name in names), "propositions": len(kb["propositions"]), "arguments": len(kb["arguments"])}


def decrypt_archive(directory: Path, passkey: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    manifest = validate_envelope(directory)
    key = derive_key(passkey, base64.b64decode(manifest["salt"]), manifest["iterations"])

    def decrypt(name: str, checksum: str | None = None) -> bytes:
        if name not in manifest["assets"]:
            raise ValueError("catalog references an unknown encrypted asset")
        raw = unseal(key, name, (directory / name).read_bytes())
        if checksum is not None and digest(raw) != checksum:
            raise ValueError("decrypted content hash mismatch")
        return raw

    catalog = json.loads(decrypt(manifest["catalog"]))
    if catalog.get("version") != 1:
        raise ValueError("unsupported catalog version")
    files: dict[str, bytes] = {}
    for entry in catalog["files"]:
        name = entry["file_name"]
        local_data_path(Path("/"), name)
        if name in files:
            raise ValueError("duplicate file in encrypted catalog")
        files[name] = decrypt(entry["asset"], entry["sha256"])
    graph = catalog["graph"]
    kb = json.loads(decrypt(graph["asset"], graph["sha256"]))
    validate_knowledge(kb, files.__getitem__)
    # The authoring file and rendered graph must describe the same knowledge.
    import tomllib
    authoring = with_session_metadata(tomllib.loads(files[DEFAULT_KNOWLEDGE].decode("utf-8")), files.__getitem__)
    if authoring != kb:
        raise ValueError("encrypted authoring TOML differs from the rendered graph")
    if "inference" in catalog:
        entry = catalog["inference"]
        validate_inference(kb, json.loads(decrypt(entry["asset"], entry["sha256"])))
    return kb, files


def unpack(directory: Path, root: Path, passkey: str) -> int:
    _, files = decrypt_archive(directory, passkey)
    # Preflight all destinations before writing anything. Never overwrite local work.
    targets = [(local_data_path(root, name), raw) for name, raw in files.items()]
    for path, raw in targets:
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("local data differs from the archive; unpack into a fresh --root instead")
    for path, raw in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return len(targets)


def copy_encrypted(root: Path, output: Path) -> bool:
    source = root / "encrypted"
    if not source.exists():
        return False
    validate_envelope(source)
    shutil.copytree(source, output / "assets" / "private")
    return True
