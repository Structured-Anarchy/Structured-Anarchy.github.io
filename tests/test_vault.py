import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from scripts.make_mock_knowledge import write_mock
from sitegen.knowledge import DEFAULT_KNOWLEDGE, digest
from sitegen.vault import copy_encrypted, decrypt_archive, pack, unpack, validate_envelope

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
