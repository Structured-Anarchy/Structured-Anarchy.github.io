"""Public, build-time link previews; never read the encrypted knowledge base."""

from datetime import date
from urllib.parse import urlsplit

from .content import ContentError, SiteConfig

SOCIAL_IMAGE = "/assets/brand/social-card.png"


def share_metadata(site: SiteConfig, path: str, title: str, description: str = "",
                   published: date | None = None, noindex: bool = False) -> dict:
    base = site.base_url.rstrip("/")
    if base:
        parts = urlsplit(base)
        if (parts.scheme not in {"https", "http"} or not parts.hostname or
                parts.username or parts.password or parts.path or parts.query or parts.fragment):
            raise ContentError("site.base_url must be an absolute HTTP(S) origin without credentials, path, query or fragment")
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise ContentError("share paths must be root-relative public page paths without queries or fragments")
    description = " ".join((description or site.description).split())
    if len(description) > 200:
        description = description[:197].rsplit(" ", 1)[0] + "…"
    return {
        "title": title,
        "description": description,
        "url": base + path if base else "",
        "image": base + SOCIAL_IMAGE if base else "",
        "image_alt": f"{site.title} — a philosophy club for shared inquiry.",
        "type": "article" if published else "website",
        "published": published.isoformat() if published else "",
        "noindex": noindex,
    }
