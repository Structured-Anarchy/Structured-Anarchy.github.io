from __future__ import annotations

import unittest
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sitegen.content import Member, SiteConfig, SiteData
from sitegen.render import build_site


ROOT = Path(__file__).resolve().parents[1]


class MembersRenderingTests(unittest.TestCase):
    def test_site_no_longer_publishes_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "site", root / "site")
            image = root / "members" / "fictional.jpg"
            image.parent.mkdir()
            image.write_bytes(b"fictional profile image")
            member = Member(slug="fictional", name="Fictional Member", last_name="Member",
                            join_date=date(2026, 1, 1), image_path=image,
                            metadata_path=image.with_suffix(".toml"), affiliations=[], interests=[], bio="Fictional bio")
            output = root / "dist"
            (output / "members").mkdir(parents=True)
            (output / "members/index.html").write_text("Previous generated member page")
            build_site(SiteData(config=SiteConfig(), members=[member], discussions=[]), root, output)
            self.assertFalse((output / "members").exists())
            self.assertFalse((output / "assets/members").exists())
            self.assertNotIn("members", json.loads((output / "site-manifest.json").read_text()))
            for page in output.rglob("*.html"):
                self.assertNotIn('href="/members/"', page.read_text())
            self.assertTrue(image.exists())

    def test_member_card_renders_profile_fields(self) -> None:
        env = Environment(
            loader=FileSystemLoader(ROOT / "site" / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )
        member = Member(
            slug="alex-rivera",
            name="Alex Rivera",
            last_name="Rivera",
            join_date=date(2026, 1, 1),
            image_path=ROOT / "alex-rivera.jpg",
            metadata_path=ROOT / "alex-rivera.toml",
            affiliations=["Community Library"],
            interests=["Ethics", "Political philosophy"],
            bio="Enjoys questions about how people live together.",
        )

        html = env.get_template("members.html").render(
            site=SiteConfig(membership_form_url="https://docs.google.com/forms/example"),
            active="members",
            members=[member],
        )

        self.assertIn('<h1 class="defocus-item">Members</h1>', html)
        self.assertIn('src="/assets/members/alex-rivera.jpg"', html)
        self.assertIn("Community Library", html)
        self.assertIn("Ethics, Political philosophy", html)
        self.assertIn("Enjoys questions about how people live together.", html)
        self.assertIn('aria-label="Structured Anarchy members"', html)
        self.assertIn('href="https://docs.google.com/forms/example"', html)
        self.assertIn(">Join Structured Anarchy</a>", html)
        self.assertIn("permission before any profile information", html)

    def test_join_prompt_is_hidden_without_a_form_url(self) -> None:
        env = Environment(
            loader=FileSystemLoader(ROOT / "site" / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )

        html = env.get_template("members.html").render(
            site=SiteConfig(),
            active="members",
            members=[],
        )

        self.assertNotIn("Join Structured Anarchy", html)


if __name__ == "__main__":
    unittest.main()
