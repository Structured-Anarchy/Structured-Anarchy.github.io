import subprocess

import pytest

from scripts.check_private_content import check, private_fragments, scan_paths


def test_scan_catches_transcript_copies_and_passkeys(tmp_path):
    private = b"Fictional private source " * 20
    page = tmp_path / "index.html"
    page.write_bytes(b"<p>" + private + b"</p>")
    assert scan_paths([page], private_fragments({"source.txt": private})) == [page]
    page.write_text("An accidentally published mock-passkey")
    assert scan_paths([page], set(), "mock-passkey") == [page]


def test_force_added_data_is_rejected(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("data/*\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret.txt").write_text("private")
    subprocess.run(["git", "add", "-f", "data/secret.txt"], cwd=tmp_path, check=True)
    with pytest.raises(ValueError, match="tracked"):
        check(tmp_path)
