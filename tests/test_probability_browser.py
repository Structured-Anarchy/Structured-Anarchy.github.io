"""Probability UI with the encrypted fictional garden/library fixture."""

from pathlib import Path

import pytest

from test_structural_map_browser import browser, mock_site, unlock, click_segment
from sitegen.inference import infer
from sitegen.knowledge import validate_local

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("width", [1440, 390, 320])
def test_probabilities_sort_circles_assumptions_and_lock(browser, mock_site, width):
    from playwright.sync_api import expect
    url, root = mock_site
    expected = infer(validate_local(root))
    page = browser.new_page(viewport={"width": width, "height": 950}, has_touch=width != 1440)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/structural-map/")
    expect(page.locator(".thesis-probability")).to_have_count(0)
    assert "garden-open" not in page.content()
    unlock(page)
    for pid in ("garden-open", "library-open"):
        expect(page.locator(f'[data-thesis="{pid}"] .thesis-probability')).to_have_text(f"P = {expected['probabilities'][pid]:.3f}")
    ids = ["garden-open", "library-open"]
    for mode, reverse in [("probability-desc", True), ("probability-asc", False)]:
        page.locator("[data-thesis-sort]").select_option(mode)
        assert page.locator("[data-thesis]").evaluate_all("rows => rows.map(r => r.dataset.thesis)") == sorted(ids, key=expected["probabilities"].get, reverse=reverse)
    page.locator("[data-thesis-search]").fill("library")
    expect(page.locator("[data-thesis]")).to_have_count(1)
    page.locator("[data-thesis-search]").fill("")
    screenshot_dir = Path("/tmp/sa-map-screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir / f"probability-list-{width}.png"), full_page=True)
    page.locator('[data-thesis="garden-open"]').click()
    expect(page.locator(".probability-value")).to_have_text(f"{expected['probabilities']['garden-open']:.3f}")
    # The centre remains clickable despite its overlaid SVG argument shells.
    page.locator(".atom-probability").click()
    dialog = page.locator("[data-evidence-dialog]")
    expect(dialog).to_contain_text("No explicit atom prior")
    expect(dialog).to_contain_text("Beta(7.2, 1)")
    expect(dialog).to_contain_text("Exact variable elimination")
    expect(page.locator("[data-speed-reader-stage]")).to_be_hidden()
    dialog.get_by_role("button", name="Close popup", exact=True).click()
    click_segment(page, "path.refute-segment")
    for card in page.locator(".atom-card").all():
        pid = card.get_attribute("data-proposition")
        expect(card.locator(".probability-value")).to_have_text(f"{expected['probabilities'][pid]:.3f}")
    page.locator('[data-proposition="garden-costly"] .atom-probability').click()
    expect(dialog).to_contain_text("Substantiated leaf premise: Beta(5, 2)")
    dialog.get_by_role("button", name="Close popup", exact=True).click()
    page.evaluate("document.activeElement.blur(); window.scrollTo({top: 0, behavior: 'instant'})")
    page.screenshot(path=str(screenshot_dir / f"probability-atoms-{width}.png"), full_page=True)
    page.locator("[data-breadcrumbs]").get_by_role("button", name="All theses", exact=True).click()
    page.locator('[data-thesis="library-open"]').click()
    segment = page.locator("path.support-segment").filter(has_text="study groups")
    segment.focus()
    page.keyboard.press("Enter")
    page.locator('[data-proposition="study-open"] .atom-probability').click()
    expect(dialog).to_contain_text("Induced leaf premise: Beta(1, 1)")
    dialog.get_by_role("button", name="Close popup", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Lock archive", exact=True).click()
    expect(page.locator(".probability-value, .thesis-probability")).to_have_count(0)
    expect(dialog.locator("[data-evidence-body]")).to_be_empty()
    stored = page.evaluate("JSON.stringify(localStorage) + JSON.stringify(sessionStorage)")
    assert "probabilities" not in stored and "garden" not in stored
    assert not errors
    page.close()


def test_probability_sort_handles_ties_missing_values_and_negation(browser, mock_site):
    url, _ = mock_site
    page = browser.new_page()
    page.goto(url + "/structural-map/")
    result = page.evaluate("""async () => {
      const {createGraphModel, sortedTheses} = await import('/assets/js/graph-model.js');
      const kb = {propositions: ['z','a','b','missing'].map(id => ({id, text:id, topics:[], origins:[]})),
        sources:[], sessions:[], arguments:[], occurrences:[], inference:{probabilities:{z:.8, a:.8, b:.2}}};
      const model = createGraphModel(kb);
      return {asc:sortedTheses(kb.propositions,'probability-asc',model).map(p => p.id),
        desc:sortedTheses(kb.propositions,'probability-desc',model).map(p => p.id),
        negated:model.probability('b',true), missing:model.probability('missing'),
        missingNegated:model.probability('missing',true)};
    }""")
    assert result == dict(asc=["b", "a", "z", "missing"], desc=["a", "z", "b", "missing"], negated=.8, missing=None, missingNegated=None)
    page.close()


def test_legacy_archive_shows_unavailable_not_fabricated_probabilities(browser, mock_site):
    from playwright.sync_api import expect
    url, _ = mock_site
    page = browser.new_page()
    # Simulate the old vault API, which returned authoring knowledge only.
    source = (ROOT / "site/assets/js/vault.js").read_text().replace("return knowledge;", "delete knowledge.inference; return knowledge;")
    page.route("**/assets/js/vault.js", lambda route: route.fulfill(body=source, content_type="text/javascript"))
    page.goto(url + "/structural-map/")
    unlock(page)
    expect(page.locator(".thesis-probability")).to_have_text(["P = —", "P = —"])
    page.locator("[data-thesis-sort]").select_option("probability-desc")
    page.locator('[data-thesis="garden-open"]').click()
    expect(page.locator(".probability-value")).to_have_text("—")
    page.locator(".atom-probability").click()
    expect(page.locator("[data-evidence-dialog]")).to_contain_text("No computed probability is included")
    page.close()


def test_negated_circle_displays_complement_not_positive_atom_probability(browser, mock_site):
    from playwright.sync_api import expect
    url, root = mock_site
    expected = infer(validate_local(root))["probabilities"]["library-open"]
    page = browser.new_page()
    # Invoke the existing signed-view entry point without changing the graph.
    source = (ROOT / "site/assets/js/structural-map.js").read_text().replace(
        "function initialize() {",
        "function initialize() { document.addEventListener('fictional-negated-view', () => openProposition('library-open', true));")
    page.route("**/assets/js/structural-map.js", lambda route: route.fulfill(body=source, content_type="text/javascript"))
    page.goto(url + "/structural-map/")
    unlock(page)
    page.evaluate("document.dispatchEvent(new Event('fictional-negated-view'))")
    expect(page.locator(".probability-caption")).to_have_text("P(¬atom)")
    expect(page.locator(".probability-value")).to_have_text(f"{1-expected:.3f}")
    page.locator(".atom-probability").click()
    expect(page.locator("[data-evidence-dialog]")).to_contain_text("1 − P(atom)")
    page.close()
