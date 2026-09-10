import json
import base64
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from scripts.make_mock_knowledge import write_mock
from sitegen.knowledge import DEFAULT_KNOWLEDGE, digest
from sitegen.vault import copy_encrypted, decrypt_archive, pack, unpack, validate_envelope
from sitegen.vault import derive_key, json_bytes, seal, unseal
from sitegen.inference import InferenceError, validate_inference

MOCK_PASSKEY = "fictional test credential — not the group passkey"


@pytest.fixture
def archive(tmp_path):
    write_mock(tmp_path)
    pack(tmp_path, tmp_path / "encrypted", MOCK_PASSKEY)
    return tmp_path


def test_roundtrip_preserves_authoring_data_and_provenance(archive, tmp_path_factory):
    kb, files = decrypt_archive(archive / "encrypted", MOCK_PASSKEY)
    assert len(kb["propositions"]) == 8
    assert files[DEFAULT_KNOWLEDGE] == (archive / DEFAULT_KNOWLEDGE).read_bytes()
    fresh = tmp_path_factory.mktemp("restore")
    assert unpack(archive / "encrypted", fresh, MOCK_PASSKEY) == 3
    for name, raw in files.items():
        assert (fresh / name).read_bytes() == raw
    assert unpack(archive / "encrypted", fresh, MOCK_PASSKEY) == 3


def test_wrong_passkey_is_rejected(archive):
    with pytest.raises(InvalidTag):
        decrypt_archive(archive / "encrypted", "wrong credential")


def test_tampering_is_rejected_even_with_updated_public_hash(archive):
    directory = archive / "encrypted"
    manifest = validate_envelope(directory)
    name = manifest["catalog"]
    raw = bytearray((directory / name).read_bytes())
    raw[15] ^= 1
    (directory / name).write_bytes(raw)
    with pytest.raises(ValueError, match="integrity check"):
        validate_envelope(directory)
    manifest["assets"][name] = digest(raw)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(InvalidTag):
        decrypt_archive(directory, MOCK_PASSKEY)


def test_export_is_opaque_and_build_copies_only_ciphertext(archive):
    directory = archive / "encrypted"
    manifest = validate_envelope(directory)
    assert len({(directory / name).read_bytes()[:12] for name in manifest["assets"]}) == len(manifest["assets"])
    for path in directory.iterdir():
        raw = path.read_bytes()
        assert b"The garden" not in raw
        assert MOCK_PASSKEY.encode() not in raw
        assert b"mock-one.txt" not in raw
    output = archive / "dist"
    output.mkdir()
    assert copy_encrypted(archive, output)
    assert sorted(p.name for p in (output / "assets/private").iterdir()) == sorted(p.name for p in directory.iterdir())


def test_unpack_never_overwrites_local_edits(archive):
    original = archive / DEFAULT_KNOWLEDGE
    original.write_bytes(original.read_bytes() + b"\n# local edit\n")
    with pytest.raises(ValueError, match="local data differs"):
        unpack(archive / "encrypted", archive, MOCK_PASSKEY)
    assert b"# local edit" in original.read_bytes()


def test_plaintext_file_in_export_is_rejected(archive):
    (archive / "encrypted" / "transcript.txt").write_text("private")
    with pytest.raises(ValueError, match="unexpected files"):
        validate_envelope(archive / "encrypted")


def test_repack_does_not_retain_old_assets(archive):
    first = set(validate_envelope(archive / "encrypted")["assets"])
    pack(archive, archive / "encrypted", MOCK_PASSKEY)
    second = set(validate_envelope(archive / "encrypted")["assets"])
    assert not first & second
    decrypt_archive(archive / "encrypted", MOCK_PASSKEY)


def edit_encrypted_catalog(archive, edit):
    """Authenticated fictional fixtures: exercise checks beyond ciphertext hashes."""
    directory = archive / "encrypted"
    manifest = validate_envelope(directory)
    key = derive_key(MOCK_PASSKEY, base64.b64decode(manifest["salt"]))
    catalog = json.loads(unseal(key, manifest["catalog"], (directory / manifest["catalog"]).read_bytes()))
    def rewrite(name, value):
        raw = json_bytes(value)
        encrypted = seal(key, name, raw)
        (directory / name).write_bytes(encrypted)
        manifest["assets"][name] = digest(encrypted)
        return digest(raw)
    edit(catalog, directory, key, rewrite)
    rewrite(manifest["catalog"], catalog)
    (directory / "manifest.json").write_bytes(json_bytes(manifest))


def test_probabilities_are_separate_encrypted_and_bound_to_authoring_graph(archive):
    kb, files = decrypt_archive(archive / "encrypted", MOCK_PASSKEY)
    def inspect(catalog, directory, key, rewrite):
        entry = catalog["inference"]
        report = json.loads(unseal(key, entry["asset"], (directory / entry["asset"]).read_bytes()))
        assert report["graph_sha256"] == catalog["graph"]["sha256"]
        assert len(report["probabilities"]) == len(kb["propositions"])
        validate_inference(kb, report)
    edit_encrypted_catalog(archive, inspect)
    assert "inference" not in kb
    assert b"probabilities" not in files[DEFAULT_KNOWLEDGE]


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(graph_sha256="0" * 64),
    lambda r: r["probabilities"].update({next(iter(r["probabilities"])): .123}),
    lambda r: r["components"][0].update(weights=[1.0] * len(r["components"][0]["weights"]), duality_gap=0),
])
def test_authenticated_but_invalid_probability_report_is_rejected(archive, mutation):
    def edit(catalog, directory, key, rewrite):
        entry = catalog["inference"]
        report = json.loads(unseal(key, entry["asset"], (directory / entry["asset"]).read_bytes()))
        mutation(report)
        entry["sha256"] = rewrite(entry["asset"], report)
    edit_encrypted_catalog(archive, edit)
    with pytest.raises(InferenceError):
        decrypt_archive(archive / "encrypted", MOCK_PASSKEY)


def test_legacy_archive_without_probability_export_still_restores(archive):
    edit_encrypted_catalog(archive, lambda catalog, *_: catalog.pop("inference"))
    kb, _ = decrypt_archive(archive / "encrypted", MOCK_PASSKEY)
    assert len(kb["propositions"]) == 8


def test_failed_inference_preserves_previous_encrypted_export(archive, monkeypatch):
    previous = {p.name: p.read_bytes() for p in (archive / "encrypted").iterdir()}
    def fail(_):
        raise InferenceError("Simulated solver failure")
    monkeypatch.setattr("sitegen.vault.infer", fail)
    with pytest.raises(InferenceError):
        pack(archive, archive / "encrypted", MOCK_PASSKEY)
    assert {p.name: p.read_bytes() for p in (archive / "encrypted").iterdir()} == previous
