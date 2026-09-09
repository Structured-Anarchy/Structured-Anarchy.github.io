"""Exercise actual Web Crypto and the complete explorer against fictional data."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading
import tomli_w

import pytest

from scripts.make_mock_knowledge import add_induced_mock, mock_knowledge, write_mock
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
    files = {s["file_name"]: (root / s["file_name"]).read_bytes() for s in kb["sources"]}
    add_induced_mock(kb, files)
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    for session, date in zip(kb["sessions"], ("2026-01-12", "2026-02-05")):
        session["metadata_file"] = f"data/knowledge/sessions/{session['id']}.toml"
        metadata = root / session["metadata_file"]
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(f'date = {date}\nlocation = "Fictional City"\n')
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
    (root / "site_config.toml").write_text('[site]\nbase_url = "https://example.test"\n')
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
    expect(dialog.locator("[data-speed-reader-context]")).to_contain_text("12 January 2026 · Fictional City")
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
    # Assertion occurrences and signed literal passages are included too.
    expect(dialog.locator(".source-passage")).to_have_count(5)
    expect(dialog).to_contain_text("5 February 2026 · Fictional City")
    page.reload()
    expect(page.locator("[data-unlock-form]")).to_be_visible()
    expect(page.locator("[data-map-content]")).to_be_hidden()
    expect(page.locator(".atom-card")).to_have_count(0)
    stored = page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert MOCK_PASSKEY not in stored and "garden" not in stored
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_recursive_counts_sort_induction_and_transcript_roundtrip(browser, mock_site, width):
    from playwright.sync_api import expect
    url, root = mock_site
    page = browser.new_page(viewport={"width": width, "height": 900}, has_touch=width == 390)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/structural-map/")
    unlock(page)
    garden = page.locator(".thesis-row").filter(has_text="garden")
    expect(garden.locator(".support-key")).to_have_text("2 support")
    expect(garden.locator(".refute-key")).to_have_text("1 refute")
    expect(garden.locator(".writing-meta")).to_contain_text("2 sessions")
    page.locator("[data-thesis-sort]").select_option("refute")
    expect(page.locator(".thesis-row").first).to_contain_text("garden")
    page.locator(".thesis-row").filter(has_text="library").click()
    segment = page.locator("path.support-segment").filter(has_text="study groups")
    segment.focus()
    page.keyboard.press("Enter")
    induced = page.locator('[data-proposition="study-open"]')
    expect(induced.locator(".induced-badge")).to_have_text("Induced · unsubstantiated")
    expect(induced.locator(".statement-source")).to_have_count(0)
    expect(page.locator(".reconstruction-note")).not_to_have_attribute("open", "")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"induced-{width}.png"), full_page=True)
    page.locator('[data-proposition="library-study"] .statement-source').click()
    dialog = page.locator("[data-evidence-dialog]")
    citation = dialog.locator(".passage-label").first
    citation.wait_for()
    href = citation.get_attribute("href")
    passage = dialog.locator(".passage-text").first.inner_text()
    dialog.locator(".passage-transcript-link").first.click()
    expect(page).to_have_url(url + href)
    expect(dialog).to_be_hidden()
    body = page.locator(".transcript-lines")
    body.wait_for()
    assert page.locator(".transcript-highlight").all_text_contents() == [passage]
    source_text = (root / "data/refined-transcripts/mock-two.txt").read_bytes().decode()
    # Rendered source lines preserve decoded codepoints, including CR and emoji.
    rendered = page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')")
    assert rendered == source_text
    marker = page.locator(".transcript-marker:visible").last
    if width == 390:
        marker.tap()
    else:
        marker.hover()
    menu = page.locator("[data-transcript-menu]")
    expect(menu).to_be_visible()
    # A full-page capture temporarily resizes the viewport and correctly closes
    # the position-dependent menu. Capture the actual viewport while it is open.
    page.screenshot(path=str(screenshot_dir / f"transcript-{width}.png"))
    menu.get_by_role("link").filter(has_text="library should stay open").click()
    expect(page.locator('[data-proposition="library-open"]')).to_be_visible()
    page.go_back()
    expect(body).to_be_visible()
    page.locator(".site-nav").get_by_role("link", name="Discussions", exact=True).click()
    expect(page.locator(".session-row")).to_have_count(2)
    expect(page.locator(".session-row")).to_have_text(["5 February 2026 · Fictional City", "12 January 2026 · Fictional City"])
    page.locator('.session-row[href$="source=source-one"]').click()
    expect(body).to_contain_text("🌿")
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(page.locator(".transcript-lines")).to_have_count(0)
    expect(menu).to_be_hidden()
    unlock(page)
    expect(body).to_be_visible()
    deep_url = page.url
    page.reload()
    expect(page.locator("[data-unlock-form]")).to_be_visible()
    assert page.url == deep_url
    assert not page.locator(".transcript-lines").count()
    assert MOCK_PASSKEY not in page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    page.close()


def test_shared_cycle_counts_deep_sessions_and_sort_modes(browser, mock_site):
    url, _ = mock_site
    kb, _ = mock_knowledge()
    kb["sources"].append(dict(id="source-three", file_name="data/refined-transcripts/mock-three.txt"))
    kb["sessions"].append(dict(id="session-three", source_ids=["source-three"]))
    # This traversal test deliberately uses only the fields the model consumes.
    kb["propositions"][4]["origins"].append(dict(file_name="data/refined-transcripts/mock-three.txt", start_char=0, stop_char=10))
    page = browser.new_page()
    page.goto(url + "/structural-map/")
    result = page.evaluate("""async kb => {
      const {createGraphModel, sortedTheses} = await import('/assets/js/graph-model.js');
      const model = createGraphModel(kb);
      const garden = model.descendants('garden-open');
      const focal = kb.propositions.filter(p => p.thesis);
      return {support:garden.support, refute:garden.refute, sessions:[...garden.sessions].sort(),
        clauses:garden.clauses.size, atoms:garden.atoms.size,
        bySupport:sortedTheses(focal, 'support', model).map(p => p.id),
        byRefute:sortedTheses(focal, 'refute', model).map(p => p.id),
        byTopic:sortedTheses(focal, 'topic', model).map(p => p.id),
        markers:model.transcriptMarkers('data/refined-transcripts/mock-three.txt').map(m => m.theses.map(p => p.id))};
    }""", kb)
    assert result == dict(support=2, refute=1, sessions=["session-one", "session-three", "session-two"],
                         clauses=3, atoms=6, bySupport=["garden-open", "library-open"],
                         byRefute=["garden-open", "library-open"], byTopic=["garden-open", "library-open"],
                         markers=[["garden-open"]])
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
    for path in ("/", "/discussions/", "/symbols-and-meaning/", "/discussions/mock-discussion/", "/404.html"):
        page.goto(url + path)
        expect(page.locator("h1")).to_be_visible()
        expect(page.locator('a[href="/members/"]')).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.goto(url + "/members/").status == 404
    page.goto(url + "/discussions/mock-discussion/")
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-stage]")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("[data-speed-reader-stage]")).to_be_hidden()
    assert errors == []
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_transcript_speed_reader_navigation_and_lock(browser, mock_site, width):
    from playwright.sync_api import expect
    url, root = mock_site
    page = browser.new_page(viewport={"width": width, "height": 900}, has_touch=width == 390)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    raw = (root / "data/refined-transcripts/mock-one.txt").read_bytes().decode()
    passage = "The garden is quiet."
    start = raw.index(passage)
    page.goto(f"{url}/discussions/#source=source-one&start={start}&stop={start + len(passage)}")
    expect(page.locator("[data-speed-reader]")).to_be_hidden()
    unlock(page)
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    stage = page.locator("[data-speed-reader-stage]")
    expect(stage).to_be_visible()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text("The garden is")
    expect(page.locator("[data-speed-reader-context]")).to_have_text("12 January 2026 · Fictional City")
    page.get_by_role("button", name="Increase WPM", exact=True).click()
    expect(page.locator("[data-speed-reader-wpm-value]")).to_have_text("310")
    page.get_by_role("button", name="Increase WPG", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text(passage)
    page.get_by_role("button", name="Increase font size", exact=True).click()
    expect(page.locator("[data-speed-reader-font-size-value]")).to_have_text("39")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"transcript-reader-{width}.png"))
    page.get_by_role("button", name="Play", exact=True).click()
    expect(page.get_by_role("button", name="Play", exact=True)).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Space")
    expect(page.get_by_role("button", name="Pause", exact=True)).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Escape")
    expect(stage).to_be_hidden()
    assert page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    page.get_by_role("button", name="← All sessions", exact=True).click()
    expect(page.locator("[data-speed-reader]")).to_be_hidden()
    expect(page.locator("[data-speed-reader-glance]")).to_be_empty()
    page.locator(".session-row").first.click()
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-context]")).to_have_text("5 February 2026 · Fictional City")
    page.get_by_role("button", name="Play", exact=True).click()
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(stage).to_be_hidden()
    expect(page.locator("[data-unlock-form]")).to_be_visible()
    expect(page.locator("[data-speed-reader-glance]")).to_be_empty()
    expect(page.locator("[data-speed-reader-context]")).to_be_empty()
    expect(page.locator("[data-speed-reader]")).to_be_hidden()
    assert not page.locator(".transcript-text").count()
    stored = page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert "garden" not in stored and MOCK_PASSKEY not in stored
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_symbol_catalog_sort_meanings_passages_and_archive_navigation(browser, mock_site, width):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": width, "height": 900}, has_touch=width == 390)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/symbols-and-meaning/")
    unlock(page)
    labels = page.locator(".symbol-row .writing-title").all_text_contents()
    assert labels == sorted(labels, key=str.casefold)
    if width == 1440:
        # Hovering an initially offscreen row must survive its automatic scroll.
        page.locator('[data-symbol="symbol-quiet"]').hover()
        expect(page.locator("[data-symbol-menu]")).to_be_visible()
        page.keyboard.press("Escape")
    page.locator("[data-symbol-sort]").select_option("meanings")
    expect(page.locator(".symbol-row").first).to_contain_text("quiet")
    expect(page.locator(".symbol-row").first.locator(".writing-meta")).to_have_text("4 meanings")
    quiet = page.locator('[data-symbol="symbol-quiet"]')
    if width == 390:
        quiet.tap()
    else:
        quiet.hover()
    popup = page.locator("[data-symbol-menu]")
    expect(popup).to_be_visible()
    expect(popup.locator(".meaning-list > li")).to_have_count(4)
    expect(popup).to_contain_text("No definition was declared")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"symbols-{width}.png"))
    popup.get_by_role("button", name="Little traffic noise; birdsong is permitted.", exact=True).click()
    dialog = page.locator("[data-evidence-dialog]")
    expect(dialog).to_be_visible()
    expect(popup).to_be_hidden()
    expect(dialog.locator(".source-passage")).to_have_count(2)
    expect(dialog.locator(".passage-label").first).to_contain_text("12 January 2026 · Fictional City")
    dialog.get_by_role("button", name="← Meanings", exact=True).click()
    expect(dialog.locator(".meaning-list > li")).to_have_count(4)
    dialog.get_by_role("button", name="An absence of all sound.", exact=True).click()
    dialog.locator(".passage-transcript-link").click()
    expect(page.locator(".transcript-highlight")).to_contain_text("absolutely silent")
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-stage]")).to_be_visible()
    page.keyboard.press("Escape")
    page.locator(".site-nav").get_by_role("link", name="Symbols and Meaning", exact=True).click()
    expect(page.locator("[data-unlock-form]")).to_be_hidden()
    expect(page.locator("[data-symbol-list]")).to_be_visible()
    page.locator("[data-symbol-sort]").select_option("alphabetical")
    assert page.locator(".symbol-row .writing-title").all_text_contents() == labels
    page.locator('[data-symbol="symbol-quiet"]').focus()
    page.keyboard.press("Enter")
    expect(popup).to_be_visible()
    page.keyboard.press("Escape")
    expect(popup).to_be_hidden()
    expect(page.locator('[data-symbol="symbol-quiet"]')).to_be_focused()
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(page.locator(".symbol-row")).to_have_count(0)
    expect(popup).to_be_empty()
    expect(dialog.locator("[data-evidence-body]")).to_be_empty()
    assert "quiet" not in page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert errors == []
    page.close()


def test_transcript_reader_keeps_words_whole_at_provenance_boundaries(browser, mock_site):
    from playwright.sync_api import expect
    url, root = mock_site
    raw = (root / "data/refined-transcripts/mock-one.txt").read_bytes().decode()
    # Deliberately highlight inside a word: the original DOM must stay exact,
    # but the reader should say "garden", not "gar" followed by "den".
    start = raw.index("garden is quiet") + 3
    page = browser.new_page()
    page.goto(f"{url}/discussions/#source=source-one&start={start}&stop={start + 2}")
    unlock(page)
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text("garden is quiet.")
    page.keyboard.press("Escape")
    expect(page.locator(".transcript-highlight")).to_have_text("de")
    assert page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    page.close()


def test_link_preview_is_available_without_javascript_or_unlocking(browser, mock_site):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(java_script_enabled=False)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(url + "/discussions/#source=source-one&start=0&stop=10")
    expect(page.locator('meta[property="og:title"]')).to_have_attribute("content", "Discussions | Structured Anarchy")
    expect(page.locator('meta[property="og:url"]')).to_have_attribute("content", "https://example.test/discussions/")
    head = page.locator("head").inner_html()
    assert "garden" not in head and "source-one" not in head and MOCK_PASSKEY not in head
    assert not any(request.endswith(".bin") for request in requests)
    response = page.request.get(url + "/assets/brand/social-card.png")
    assert response.status == 200 and response.headers["content-type"].startswith("image/png")
    assert page.request.get(url + "/favicon.ico").status == 200
    assert page.request.get(url + "/assets/brand/icon.svg").headers["content-type"].startswith("image/svg+xml")
    page.close()
