from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from sitegen.content import Writing
from sitegen.render import copy_writing_assets


class RenderAssetTests(unittest.TestCase):
    def test_writing_assets_are_copied_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "dist"
            entry = root / "discussions" / "first-question"
            (entry / "images").mkdir(parents=True)
            source = entry / "first-question.md"
            metadata = entry / "first-question.toml"
            asset = entry / "images" / "figure.png"
            source.write_text("source", encoding="utf-8")
            metadata.write_text("metadata", encoding="utf-8")
            asset.write_bytes(b"image")
            writing = Writing(
                section="discussions",
                slug="first-question",
                title="First question",
                date_published=date(2026, 1, 1),
                markdown_path=source,
                metadata_path=metadata,
                html="<p>First question</p>",
                excerpt="First question",
                comment_id="discussions/first-question",
            )

            copy_writing_assets(root, output, [writing])

            target = output / "assets" / "content" / "discussions" / "first-question"
            self.assertTrue((target / "images" / "figure.png").exists())
            self.assertFalse((target / "first-question.md").exists())
            self.assertFalse((target / "first-question.toml").exists())


if __name__ == "__main__":
    unittest.main()
