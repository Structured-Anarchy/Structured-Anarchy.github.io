from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import shutil

from PIL import Image
import pytest

from sitegen.content import ContentError, SiteConfig, SiteData, Writing, load_config
from sitegen.render import build_site
from sitegen.sharing import share_metadata

ROOT = Path(__file__).resolve().parents[1]


class HeadMetadata(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and (key := attrs.get("property", attrs.get("name"))):
            assert key not in self.meta, f"duplicate metadata: {key}"
            self.meta[key] = attrs.get("content")
        elif tag == "link":
            self.links.append(attrs)


@pytest.fixture
def shared_site(tmp_path):
    shutil.copytree(ROOT / "site", tmp_path / "site")
    source = tmp_path / "discussions/fictional-question"
    source.mkdir(parents=True)
    markdown = source / "fictional-question.md"
    metadata = source / "fictional-question.toml"
    markdown.write_text("Fictional public note.")
    metadata.write_text('title = "Fictional public note"\n')
    note = Writing(section="discussions", slug="fictional-question", title='A "question" & an answer',
                   date_published=date(2026, 1, 12), markdown_path=markdown, metadata_path=metadata,
                   html="<p>Fictional public note.</p>", excerpt='A fictional "description" & <example>.',
                   comment_id="discussions/fictional-question")
    config = SiteConfig(title="Fictional Club", base_url="https://example.test/", description="A fictional public club description.")
    build_site(SiteData(config=config, members=[], discussions=[note]), tmp_path, tmp_path / "dist")
    return tmp_path / "dist"


@pytest.mark.parametrize("path,title,kind", [
    ("/", "Fictional Club", "website"),
    ("/discussions/", "Discussions | Fictional Club", "website"),
    ("/structural-map/", "Structural Map | Fictional Club", "website"),
    ("/symbols-and-meaning/", "Symbols and Meaning | Fictional Club", "website"),
    ("/discussions/fictional-question/", 'A "question" & an answer | Fictional Club', "article"),
    ("/404.html", "Page not found | Fictional Club", "website"),
])
def test_public_page_metadata_is_complete_and_escaped(shared_site, path, title, kind):
    file = shared_site / (path.lstrip("/") + "index.html" if path.endswith("/") else path.lstrip("/"))
    html = file.read_text()
    head = HeadMetadata(html)
    assert head.meta["og:title"] == head.meta["twitter:title"] == title
    assert head.meta["og:description"] == head.meta["twitter:description"] == head.meta["description"]
    assert head.meta["description"]
    assert head.meta["og:site_name"] == "Fictional Club"
    assert head.meta["og:type"] == kind
    assert head.meta["og:url"] == "https://example.test" + path
    assert next(link["href"] for link in head.links if link.get("rel") == "canonical") == head.meta["og:url"]
    assert head.meta["og:image"] == head.meta["twitter:image"] == "https://example.test/assets/brand/social-card.png"
    assert head.meta["og:image:alt"] == head.meta["twitter:image:alt"]
    assert head.meta["og:image:width"] == "1200"
    assert head.meta["og:image:height"] == "630"
    assert head.meta["og:image:type"] == "image/png"
    assert head.meta["twitter:card"] == "summary_large_image"
    if kind == "article":
        assert head.meta["description"] == 'A fictional "description" & <example>.'
        assert head.meta["article:published_time"] == "2026-01-12"
        # Sharing titles must not change the existing giscus discussion mapping.
        assert "<title>[discussion/comments] discussions/fictional-question</title>" in html
    if path == "/404.html":
        assert head.meta["robots"] == "noindex, follow"
    for link in head.links:
        if link.get("rel") in {"icon", "apple-touch-icon"}:
            assert (shared_site / link["href"].lstrip("/")).is_file()


def test_public_images_and_icon_formats_are_copied_intact(shared_site):
    with Image.open(shared_site / "assets/brand/social-card.png") as image:
        assert image.size == (1200, 630)
        assert image.format == "PNG"
    assert (shared_site / "assets/brand/social-card.png").stat().st_size < 1_000_000
    with Image.open(shared_site / "assets/brand/icon-32.png") as image:
        assert image.size == (32, 32)
    with Image.open(shared_site / "assets/brand/apple-touch-icon.png") as image:
        assert image.size == (180, 180)
        assert image.mode == "RGB"
    with Image.open(shared_site / "favicon.ico") as image:
        assert image.ico.sizes() == {(16, 16), (32, 32), (48, 48)}
    assert (shared_site / "favicon.ico").read_bytes() == (shared_site / "assets/brand/favicon.ico").read_bytes()
    assert not (shared_site / "branding").exists()


@pytest.mark.parametrize("url", ["example.test", "//example.test", "javascript:alert(1)",
                                    "https://example.test/path", "https://example.test/?q=value",
                                    "https://example.test/#fragment", "https://user:password@example.test"])
def test_invalid_public_origins_are_rejected(url):
    with pytest.raises(ContentError, match="base_url"):
        share_metadata(SiteConfig(base_url=url), "/", "Public title")


@pytest.mark.parametrize("path", ["relative", "//example.test/", "/#private-id", "/?secret=value"])
def test_canonical_paths_cannot_contain_private_fragments_or_queries(path):
    with pytest.raises(ContentError, match="share paths"):
        share_metadata(SiteConfig(base_url="https://example.test"), path, "Public title")


def test_missing_base_url_does_not_invent_a_canonical_origin():
    sharing = share_metadata(SiteConfig(), "/", "Public title")
    assert sharing["url"] == sharing["image"] == ""


def test_description_configuration_and_normalization(tmp_path):
    (tmp_path / "site_config.toml").write_text('[site]\nbase_url = "https://example.test"\ndescription = "Public club description"\n')
    config = load_config(tmp_path)
    assert share_metadata(config, "/", "Club")["description"] == "Public club description"
    long_text = "Fictional paragraph.\n" * 30
    description = share_metadata(config, "/", "Club", long_text)["description"]
    assert "\n" not in description and len(description) <= 200
    assert description.endswith("…")
