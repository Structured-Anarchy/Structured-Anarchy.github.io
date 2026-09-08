"""Exercise actual Web Crypto and the complete explorer against fictional data."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading
import tomli_w

import pytest

from scripts.make_mock_knowledge import write_mock
from sitegen.build import build
from sitegen.vault import pack
from sitegen.knowledge import DEFAULT_KNOWLEDGE, make_origin

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[1]
MOCK_PASSKEY = "fictional browser test passkey"


@pytest.fixture(scope="module")
def mock_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("browser-site")
    kb = write_mock(root)
    # Overlapping evidence must be read once in the union, not repeated.
    thesis = next(p for p in kb["propositions"] if p["id"] == "garden-open")
    origin = thesis["origins"][0]
    raw = (root / origin["file_name"]).read_bytes()
    thesis["origins"].append(make_origin(origin["file_name"], raw, origin["start_char"] + 4, origin["stop_char"]))
    (root / DEFAULT_KNOWLEDGE).write_text(tomli_w.dumps(kb))
    shutil.copytree(ROOT / "site", root / "site")
    # Discussion detail exists only in this synthetic preview, not on the real site.
    discussion = root / "discussions" / "mock-discussion"
    discussion.mkdir(parents=True)
    (discussion / "mock-discussion.md").write_text("A fictional discussion used to test the existing speed reader.")
    (discussion / "mock-discussion.toml").write_text('title = "Fictional discussion"\ndate_published = "2026-01-01"\n')
    pack(root, root / "encrypted", MOCK_PASSKEY)
    build(root, root / "dist")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root / "dist")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", root
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


def unlock(page):
    page.locator("#content-passkey").fill(MOCK_PASSKEY)
    page.get_by_role("button", name="Unlock", exact=True).click()
    page.locator("[data-map-content]").wait_for(state="visible")


def click_segment(page, selector):
    # The bounding-box midpoint of a hollow arc is in its hole. Click its visible
    # +/- label, which sits on the painted ring and passes events to the path.
    segment = page.locator(selector)
    segment.scroll_into_view_if_needed()
    point = segment.evaluate("""path => {
      const label = path.nextElementSibling;
      const point = new DOMPoint(Number(label.getAttribute('x')), Number(label.getAttribute('y')) - 5);
      const screen = point.matrixTransform(path.ownerSVGElement.getScreenCTM());
      return { x: screen.x, y: screen.y };
    }""")
    page.mouse.click(point["x"], point["y"])


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}])
def test_unlock_graph_meanings_passages_and_refresh(browser, mock_site, viewport):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport=viewport)
    errors = []
    requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(url + "/structural-map/")
    expect(page.locator("#content-passkey")).to_have_attribute("type", "text")
    expect(page.locator("[data-map-content]")).to_be_hidden()
    page.locator("#content-passkey").fill("incorrect")
    page.get_by_role("button", name="Unlock", exact=True).click()
    expect(page.locator("#vault-status")).to_contain_text("did not unlock")
    unlock(page)
    expect(page.locator(".thesis-row")).to_have_count(2)
    expect(page.locator("#content-passkey")).to_have_value("")
    # Only the catalog and graph decrypt at unlock; source files are lazy.
    initial_assets = set(request for request in requests if request.endswith(".bin"))
    assert len(initial_assets) == 2
    page.locator(".thesis-row").filter(has_text="garden").click()
    expect(page.locator(".atom-card")).to_have_count(1)
    expect(page.locator("path.support-segment")).to_have_count(1)
    expect(page.locator("path.refute-segment")).to_have_count(1)
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"thesis-{viewport['width']}.png"), full_page=True)
    click_segment(page, "path.support-segment")
    expect(page.locator(".atom-card")).to_have_count(2)
    page.screenshot(path=str(screenshot_dir / f"premises-{viewport['width']}.png"), full_page=True)
    quiet = page.locator('[data-proposition="garden-quiet"] .statement-symbol').filter(has_text="quiet")
    quiet.hover()
    expect(page.locator("[data-meaning-preview]")).to_be_visible()
    page.mouse.move(0, 0)
    expect(page.locator("[data-meaning-preview]")).to_be_hidden()
    quiet.click()
    dialog = page.locator("[data-evidence-dialog]")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("deliberately used together")
    dialog.locator("summary").filter(has_text="Other meanings").click()
    expect(dialog).to_contain_text("Explicitly excluded: An absence of all sound.")
    dialog.get_by_role("button", name="Little traffic noise; birdsong is permitted.", exact=True).click()
    expect(dialog.locator(".source-passage")).to_have_count(2)
    expect(dialog).to_contain_text("Birdsong is permitted")
    page.screenshot(path=str(screenshot_dir / f"passages-{viewport['width']}.png"))
    assert len(set(request for request in requests if request.endswith(".bin"))) == 3
    dialog.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(dialog.locator("[data-speed-reader-stage]")).to_be_visible()
    expect(dialog.locator("[data-speed-reader-context]")).to_contain_text("Fictional session one")
    dialog.get_by_role("button", name="Play", exact=True).click()
    expect(dialog.get_by_role("button", name="Play", exact=True)).to_have_attribute("aria-pressed", "true")
    dialog.get_by_role("button", name="Turn off speed reading", exact=True).click()
    dialog.get_by_role("button", name="← Meanings", exact=True).click()
    expect(dialog.locator(".source-passage")).to_have_count(0)
    expect(dialog.locator("[data-speed-reader-stage]")).to_be_hidden()
    dialog.get_by_role("button", name="Close popup", exact=True).click()
    click_segment(page, '[data-proposition="garden-quiet"] path.support-segment')
    expect(page.get_by_role("button", name="Already on this path — return ↑")).to_be_visible()
    page.get_by_role("button", name="Already on this path — return ↑").click()
    click_segment(page, "path.refute-segment")
    expect(page.locator(".atom-card")).to_have_count(2)
    expect(page.locator("[data-argument-context]")).to_contain_text("¬(The garden should stay open.)")
    page.get_by_role("button", name="Go up one view").click()
    page.locator(".statement-source").click()
    expect(dialog.locator(".source-passage")).to_have_count(2)
    expect(dialog).to_contain_text("Fictional session two")
    page.reload()
    expect(page.locator("[data-unlock-form]")).to_be_visible()
    expect(page.locator("[data-map-content]")).to_be_hidden()
    expect(page.locator(".atom-card")).to_have_count(0)
    stored = page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert MOCK_PASSKEY not in stored and "garden" not in stored
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    page.close()


def test_permalink_keyboard_shared_uses_and_manual_lock(browser, mock_site):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(url + "/structural-map/#garden-open")
    unlock(page)
    expect(page.locator('[data-proposition="garden-open"]')).to_be_visible()
    page.locator("path.support-segment").focus()
    page.keyboard.press("Enter")
    principle = page.locator('[data-proposition="quiet-open"]')
    principle.locator("summary").click()
    principle.get_by_role("button", name="The library should stay open.", exact=True).click()
    expect(page.locator('[data-proposition="library-open"]')).to_be_visible()
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(page.locator("[data-unlock-form]")).to_be_visible()
    expect(page.locator(".atom-card")).to_have_count(0)
    expect(page.locator("[data-evidence-dialog]")).to_be_hidden()
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_existing_pages_and_speed_reader(browser, mock_site, width):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for path in ("/", "/discussions/", "/discussions/mock-discussion/", "/members/", "/404.html"):
        page.goto(url + path)
        expect(page.locator("h1")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.goto(url + "/discussions/mock-discussion/")
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-stage]")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("[data-speed-reader-stage]")).to_be_hidden()
    assert errors == []
    page.close()
