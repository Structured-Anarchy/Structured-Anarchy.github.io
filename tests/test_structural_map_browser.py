"""Exercise actual Web Crypto and the complete explorer against fictional data."""

from functools import partial
from copy import deepcopy
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
    for identifier, kind in (("question-review", "extraction_review"), ("question-legacy", None)):
        question = deepcopy(kb["questions"][0])
        question.update(id=identifier, text=f"Private reviewer prompt: {identifier}")
        question.pop("session_id")
        if kind:
            question["origin_kind"] = kind
        else:
            question.pop("origin_kind")
        kb["questions"].append(question)
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


@pytest.mark.parametrize("width", [1440, 390])
def test_only_session_questions_and_other_thesis_links(browser, mock_site, width):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": width, "height": 950})
    page.goto(url + "/structural-map/#garden-open")
    unlock(page)
    # Cycles must not suggest the current thesis as an alternative use.
    expect(page.locator('[data-proposition="garden-open"] .other-uses')).to_have_count(0)
    click_segment(page, "path.support-segment")
    shared = page.locator('[data-proposition="quiet-open"] .other-uses')
    expect(shared.locator("summary")).to_have_text("Also used in 1 thesis")
    shared.locator("summary").click()
    expect(shared.get_by_role("button")).to_have_count(1)
    shared.get_by_role("button", name="The library should stay open.", exact=True).click()
    expect(page.locator('[data-proposition="library-open"]')).to_have_count(1)
    page.goto(url + "/structural-map/#garden-costly")
    # Fragment navigation retains the unlocked in-memory archive.
    expect(page.locator(".open-question")).to_have_count(1)
    expect(page.locator(".open-question")).to_have_text("Open question: What do we mean by costly?")
    assert "Private reviewer prompt" not in page.locator("body").inner_text()
    page.locator(".open-question").click()
    expect(page.locator(".source-passage")).to_have_count(1)
    expect(page.locator("[data-evidence-dialog]")).to_contain_text("What do we mean by costly?")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.close()


def test_other_theses_include_indirect_users_and_deduplicate_cycles(browser, mock_site):
    url, _ = mock_site
    page = browser.new_page()
    page.goto(url + "/structural-map/")
    result = page.evaluate("""async () => {
      const { createGraphModel } = await import('/assets/js/graph-model.js');
      const p = (id, thesis) => ({ id, text: id, thesis, origins: [] });
      const a = (id, premise, head) => ({ id, premises: [{ proposition_id: premise, origins: [] }], conclusion: { proposition_id: head, negated: false, origins: [] } });
      const kb = { sources: [], sessions: [], occurrences: [],
        propositions: [p('current', true), p('shared', false), p('middle', false), p('other', true), p('third', true), p('unrelated', true)],
        arguments: [a('a', 'shared', 'current'), a('b', 'shared', 'middle'), a('c', 'middle', 'other'), a('d', 'other', 'middle'), a('e', 'shared', 'other'), a('f', 'shared', 'third')] };
      return createGraphModel(kb).otherTheses('shared', 'current').map(p => p.id);
    }""")
    assert result == ["other", "third"]
    page.close()


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
    expect(page.locator("[data-thesis-list] > .map-note")).to_have_count(0)
    page.locator("[data-thesis-sort]").select_option("refute")
    expect(page.locator(".thesis-row").first).to_contain_text("garden")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"thesis-list-{width}.png"), full_page=True)
    page.locator(".thesis-row").filter(has_text="library").click()
    segment = page.locator("path.support-segment").filter(has_text="study groups")
    segment.focus()
    page.keyboard.press("Enter")
    induced = page.locator('[data-proposition="study-open"]')
    expect(induced.locator(".induced-badge")).to_have_text("Induced · unsubstantiated")
    expect(induced.locator(".statement-source")).to_have_count(0)
    expect(page.locator(".reconstruction-note")).not_to_have_attribute("open", "")
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


def test_independent_opposition_counts_include_contested_premises(browser, mock_site):
    from test_competing_arguments import competing_knowledge
    url, _ = mock_site
    kb, _ = competing_knowledge()
    page = browser.new_page()
    page.goto(url + "/structural-map/")
    result = page.evaluate("""async kb => {
      const {createGraphModel} = await import('/assets/js/graph-model.js');
      const model = createGraphModel(kb);
      const root = model.descendants('marked-passable');
      const premise = model.descendants('unlocked-passable');
      return {root:[root.support, root.refute, root.clauses.size],
              premise:[premise.support, premise.refute, premise.clauses.size]};
    }""", kb)
    # Shared bypass and north-gate facts are reused, not separately counted as rules.
    assert result == dict(root=[3, 3, 6], premise=[1, 1, 2])
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
    expect(page.locator("[data-symbol-sort]")).to_have_value("meanings")
    labels = page.locator(".symbol-row .writing-title").all_text_contents()
    counts = [int(text.split()[0]) for text in page.locator(".symbol-row .writing-meta").all_text_contents()]
    rows = list(zip(counts, labels))
    assert rows == sorted(rows, key=lambda row: (-row[0], row[1].casefold()))
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"symbols-default-{width}.png"))
    page.locator("[data-symbol-sort]").select_option("alphabetical")
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
    # Focus scrolls this offscreen row into view. Let that scroll event finish
    # before Enter opens a popup which intentionally closes on scrolling.
    page.evaluate("() => new Promise(requestAnimationFrame)")
    page.keyboard.press("Enter")
    expect(popup).to_be_visible()
    page.keyboard.press("Escape")
    expect(popup).to_be_hidden()
    expect(page.locator('[data-symbol="symbol-quiet"]')).to_be_focused()
    page.reload()
    unlock(page)
    expect(page.locator("[data-symbol-sort]")).to_have_value("meanings")
    expect(page.locator(".symbol-row").first).to_contain_text("quiet")
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


def render_timestamp_example(page, text, start=None, stop=None, markers=()):
    """Exercise uncommon source layouts without changing the encrypted fixture."""
    page.evaluate("""async ({text, start, stop, markers}) => {
      const {createTranscriptView} = await import('/assets/js/transcripts.js');
      window.timestampExample?.clear();
      document.querySelector('#timestamp-example-menu')?.remove();
      const menu = document.querySelector('[data-transcript-menu]').cloneNode();
      menu.id = 'timestamp-example-menu';
      menu.removeAttribute('data-transcript-menu');
      document.body.append(menu);
      window.timestampExample = createTranscriptView(
        document.querySelector('[data-transcript-body]'),
        menu,
        {source: async () => text}, () => {});
      await window.timestampExample.show(
        {id: 'timestamp-example', file_name: 'fictional.txt', label: 'Fictional session'},
        {transcriptMarkers: () => markers}, start, stop);
    }""", dict(text=text, start=start, stop=stop, markers=markers))


@pytest.mark.parametrize("width", [1440, 390, 320])
@pytest.mark.parametrize("estimated", [False, True])
def test_transcript_intro_cleanup_preserves_notes_reading_and_citations(browser, mock_site, width, estimated):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": width, "height": 950}, has_touch=width != 1440)
    page.goto(url + "/discussions/#source=source-one")
    unlock(page)
    page.locator(".transcript-lines").wait_for()
    title = "SECOND-PASS REFINED TRANSCRIPT"
    if estimated:
        title = "\ufeff" + title + " — ESTIMATED TIMESTAMPS"
    note = "Timing note: times are estimated." if estimated else "Editorial note: wording is preserved."
    newline = "\r\n" if estimated else "\n"
    raw = newline.join([title, "Source: fictional-🌿.txt", "", note, "", "00:05", "The garden is quiet.", ""])
    render_timestamp_example(page, raw)
    body = page.locator("[data-transcript-body]")
    expect(body.locator(".transcript-title")).to_have_text("Fictional session")
    expect(body.locator(":scope > p")).to_have_count(0)
    expect(page.locator(".transcript-text:visible").first).to_have_text(note)
    assert "SECOND-PASS" not in body.inner_text()
    assert "fictional-🌿.txt" not in body.inner_text()
    assert page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    if not estimated and width in (1440, 390):
        screenshot_dir = Path("/tmp/sa-map-screenshots")
        screenshot_dir.mkdir(exist_ok=True)
        page.locator("[data-transcript-view]").screenshot(path=str(screenshot_dir / f"transcript-intro-{width}.png"))
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text(" ".join(note.split()[:3]), use_inner_text=True)
    page.keyboard.press("Escape")
    # Existing codepoint links still highlight and read the exact spoken text,
    # even with an astral character in the hidden filename and CRLF newlines.
    start = raw.index("The garden")
    stop = start + len("The garden is quiet.")
    markers = [dict(start=start, theses=[dict(id="garden-open", text="The garden should stay open.")])]
    render_timestamp_example(page, raw, start, stop, markers)
    expect(page.locator(".transcript-highlight")).to_have_text(raw[start:stop])
    marker = page.locator(".transcript-marker:visible")
    expect(marker).to_have_attribute("data-passage-start", str(start))
    if width == 1440:
        marker.hover()
    else:
        marker.tap()
    expect(page.locator("#timestamp-example-menu a")).to_have_attribute("href", "/structural-map/#garden-open")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text("The garden is")
    page.keyboard.press("Escape")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.close()


@pytest.mark.parametrize("raw", [
    "Editorial note: wording is preserved.\nSource: a speaker's example.\n",
    "SECOND-PASS REFINED TRANSCRIPT\nThis is spoken text without a source header.\n",
    "A speaker quotes an export:\nSECOND-PASS REFINED TRANSCRIPT\nSource: fictional.txt\n",
])
def test_transcript_intro_cleanup_leaves_other_text_visible(browser, mock_site, raw):
    url, _ = mock_site
    page = browser.new_page()
    page.goto(url + "/discussions/#source=source-one")
    unlock(page)
    page.locator(".transcript-lines").wait_for()
    render_timestamp_example(page, raw)
    assert page.locator(".transcript-line:visible .transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    page.close()


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_timestamp_margins_preserve_source_and_share_marker_rows(browser, mock_site, width):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page(viewport={"width": width, "height": 950}, has_touch=width != 1440)
    page.goto(url + "/discussions/#source=source-one")
    unlock(page)
    page.locator(".transcript-lines").wait_for()
    # CRLF, astral Unicode, estimates, and bracketed inline times all keep
    # their original codepoint positions. A time in speech is not an annotation.
    raw = ("00:05\r\n🌿 The garden is quiet.\r\n\r\n"
           "~01:02:03\nThe library is quiet.\n\n"
           "[00:25] We meet at 12:30 today.\n"
           "01:02:09\nQuiet places should stay open.\n")
    start = raw.index("~01:02:03")
    speech = raw.index("The library")
    stop = speech + len("The library is quiet.")
    markers = [
        dict(start=start, theses=[dict(id="garden-open", text="The garden should stay open.")]),
        dict(start=speech, theses=[dict(id="library-open", text="The library should stay open.")]),
    ]
    render_timestamp_example(page, raw, start, stop, markers)
    expect(page.locator(".transcript-timestamp")).to_have_count(4)
    expect(page.locator(".transcript-time-row")).to_have_count(3)
    assert page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    expect(page.locator(".transcript-highlight")).to_have_text("The library is quiet.")
    expect(page.locator(".transcript-time-highlight")).to_have_text("~01:02:03")
    # All timestamps are left of the marker gutter, and collapsed standalone
    # timecodes align with the following source line without taking a text row.
    assert page.locator(".transcript-timestamp").evaluate_all("""stamps => stamps.every(stamp => {
      const row = stamp.closest('.transcript-line');
      const box = stamp.getBoundingClientRect();
      const text = row.querySelector('.transcript-text').getBoundingClientRect();
      return box.left >= 0 && box.right <= text.left - 44 &&
        (!row.classList.contains('transcript-time-row') ||
          Math.abs(box.top - row.nextElementSibling.getBoundingClientRect().top) < 1);
    })""")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    marker = page.locator(".transcript-marker:visible")
    expect(marker).to_have_count(1)
    expect(marker).to_have_attribute("aria-label", "2 theses using passages starting on this row")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.locator("[data-transcript-view]").screenshot(path=str(screenshot_dir / f"timestamp-margins-{width}.png"))
    if width == 1440:
        marker.hover()
    else:
        marker.tap()
    expect(page.locator("#timestamp-example-menu a")).to_have_count(2)
    page.keyboard.press("Escape")
    # A linked turn starting at its timecode must read the spoken passage.
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text("The library is")
    page.keyboard.press("Escape")
    # Selection still chooses a different spoken starting point.
    page.locator(".transcript-text").filter(has_text="We meet").evaluate("""element => {
      const text = [...element.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.includes('We meet'));
      const range = document.createRange();
      range.selectNodeContents(text);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
    }""")
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    expect(page.locator("[data-speed-reader-glance]")).to_have_text("We meet at")
    page.keyboard.press("Escape")
    page.close()


def test_speed_reader_skips_timecodes_throughout_playback(browser, mock_site):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page()
    page.goto(url + "/discussions/#source=source-one")
    unlock(page)
    page.locator(".transcript-lines").wait_for()
    raw = "00:01\nAlpha beta.\n~01:02:03\nGamma delta.\n[00:04] Meet at 12:30."
    render_timestamp_example(page, raw)
    page.clock.install()
    page.get_by_role("button", name="Turn on speed reading", exact=True).click()
    page.get_by_role("button", name="Decrease WPG", exact=True).click(click_count=2)
    page.get_by_role("button", name="Play", exact=True).click()
    for index, word in enumerate(["Alpha", "beta.", "Gamma", "delta.", "Meet", "at", "12:30."]):
        if index:
            page.clock.run_for(200)
        expect(page.locator("[data-speed-reader-glance]")).to_have_text(word)
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(page.locator(".transcript-timestamp")).to_have_count(0)
    expect(page.locator("[data-speed-reader-glance]")).to_be_empty()
    page.close()


@pytest.mark.parametrize("raw, stamps, collapsed", [
    ("00:01\n00:02\nSpeech.\n00:03", 3, 1),
    ("00:01\n\nSpeech.\n", 1, 0),
    ("[~01:02:03]\r\nSpeech.\r\n", 1, 1),
    ("We meet at 12:30.\n12:30 is our meeting time.\n[00:99] Invalid time.\n", 0, 0),
])
def test_timestamp_layout_edge_cases(browser, mock_site, raw, stamps, collapsed):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page()
    page.goto(url + "/discussions/#source=source-one")
    unlock(page)
    page.locator(".transcript-lines").wait_for()
    render_timestamp_example(page, raw)
    expect(page.locator(".transcript-timestamp")).to_have_count(stamps)
    expect(page.locator(".transcript-time-row")).to_have_count(collapsed)
    assert page.locator(".transcript-text").evaluate_all("rows => rows.map(r => r.textContent).join('\\n')") == raw
    boxes = page.locator(".transcript-timestamp").evaluate_all("stamps => stamps.map(s => { const r = s.getBoundingClientRect(); return {top:r.top, bottom:r.bottom}; })")
    assert all(first["bottom"] <= second["top"] + 1 for first, second in zip(boxes, boxes[1:]))
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
