#!/usr/bin/env python3
"""Render the public vector icon and share card. No private data is read.

Requires requirements-test.txt and Playwright's Chromium only when regenerating
the checked-in PNG/ICO assets; the normal site build just copies these assets.
"""

from io import BytesIO
import base64
from pathlib import Path
import sys
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sitegen.content import load_config


def generate() -> None:
    assets = ROOT / "site/assets"
    brand = assets / "brand"
    site = load_config(ROOT)
    env = Environment(loader=FileSystemLoader(ROOT / "site/branding"), autoescape=select_autoescape(["html"]))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=1)
        page.goto((brand / "icon.svg").as_uri())
        icon = Image.open(BytesIO(page.screenshot(omit_background=True))).convert("RGBA")
        icon.resize((32, 32), Image.Resampling.LANCZOS).save(brand / "icon-32.png", optimize=True)
        touch_icon = Image.new("RGB", icon.size, "#fbfaf5")
        touch_icon.paste(icon, mask=icon.getchannel("A"))
        touch_icon.resize((180, 180), Image.Resampling.LANCZOS).save(brand / "apple-touch-icon.png", optimize=True)
        icon.save(brand / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        page.set_viewport_size({"width": 1200, "height": 630})
        page.goto("about:blank")
        def data_url(path: Path, mime: str) -> str:
            return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

        html = env.get_template("social-card.html").render(
            site=site, domain=urlsplit(site.base_url).netloc,
            icon=data_url(brand / "icon.svg", "image/svg+xml"),
            font_regular=data_url(assets / "fonts/cormorant-regular.woff2", "font/woff2"),
            font_semibold=data_url(assets / "fonts/cormorant-semibold.woff2", "font/woff2"),
        )
        page.set_content(html)
        page.evaluate("document.fonts.ready")
        page.locator("img").evaluate("image => image.decode()")
        page.screenshot(path=str(brand / "social-card.png"))
        browser.close()
    print("Generated public social card, favicon and touch icon.")


if __name__ == "__main__":
    generate()
