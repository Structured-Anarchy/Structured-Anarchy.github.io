from datetime import date

import pytest
import tomli_w

from scripts.make_mock_knowledge import write_mock
from sitegen.knowledge import DEFAULT_KNOWLEDGE, validate_local
from sitegen.sessions import with_session_metadata
from sitegen.vault import decrypt_archive, pack, unpack


def metadata_graph():
    return {"sessions": [{"id": "session-one", "title": "Old source title",
                           "source_ids": ["source-one"],
                           "metadata_file": "data/knowledge/sessions/session-one.toml"}]}


def test_metadata_owns_title_and_date_without_mutating_authoring():
    original = metadata_graph()
    original["sources"] = [{"id": "source-one", "label": "Old refined version label"}]
    result = with_session_metadata(original, lambda _: b'date = 2026-01-12\nlocation = "Fictional City"\n')
    assert result["sessions"][0]["title"] == "12 January 2026 · Fictional City"
    assert result["sessions"][0]["date"] == "2026-01-12"
    assert result["sessions"][0]["location"] == "Fictional City"
    assert original["sessions"][0]["title"] == "Old source title"
    assert "date" not in original["sessions"][0]
    assert result["sources"][0]["label"] == result["sessions"][0]["title"]
    assert original["sources"][0]["label"] == "Old refined version label"


@pytest.mark.parametrize("metadata", [
    {"date": "2026-02-30", "location": "Fictional City"},
    {"date": "20260112", "location": "Fictional City"},
    {"date": "2026-01-12T12:00:00", "location": "Fictional City"},
    {"date": date(2026, 1, 12), "location": "  "},
    {"date": date(2026, 1, 12), "location": 123},
    {"date": date(2026, 1, 12)},
    {"date": date(2026, 1, 12), "location": "Fictional City", "extra": "unsupported"},
])
def test_invalid_metadata_is_rejected(metadata):
    with pytest.raises(ValueError):
        with_session_metadata(metadata_graph(), lambda _: tomli_w.dumps(metadata).encode())


@pytest.mark.parametrize("path", ["data/../secret.toml", "data/knowledge/sessions/session-two.toml", "/tmp/session-one.toml"])
def test_metadata_cannot_escape_or_reference_another_session(path):
    kb = metadata_graph()
    kb["sessions"][0]["metadata_file"] = path
    with pytest.raises(ValueError, match="session metadata must use"):
        with_session_metadata(kb, lambda _: pytest.fail("Invalid path must not be read"))


def test_metadata_roundtrip_and_edits(tmp_path):
    kb = write_mock(tmp_path)
    kb["sessions"][0]["metadata_file"] = metadata_graph()["sessions"][0]["metadata_file"]
    metadata = tmp_path / kb["sessions"][0]["metadata_file"]
    metadata.parent.mkdir(parents=True)
    metadata.write_text('date = 2026-01-12\nlocation = "Fictional City"\n')
    authoring = tmp_path / DEFAULT_KNOWLEDGE
    authoring.write_text(tomli_w.dumps(kb))
    original = authoring.read_bytes()
    pack(tmp_path, tmp_path / "encrypted", "fictional metadata test key")
    rendered, files = decrypt_archive(tmp_path / "encrypted", "fictional metadata test key")
    assert rendered["sessions"][0]["title"] == "12 January 2026 · Fictional City"
    assert files[kb["sessions"][0]["metadata_file"]] == metadata.read_bytes()
    assert files[DEFAULT_KNOWLEDGE] == original
    unpack(tmp_path / "encrypted", tmp_path / "restored", "fictional metadata test key")
    assert validate_local(tmp_path / "restored") == rendered
    metadata.write_text('date = "2026-02-05"\nlocation = "Another Fictional City"\n')
    assert validate_local(tmp_path)["sessions"][0]["title"] == "5 February 2026 · Another Fictional City"
    assert authoring.read_bytes() == original
    metadata.unlink()
    with pytest.raises(FileNotFoundError):
        validate_local(tmp_path)
