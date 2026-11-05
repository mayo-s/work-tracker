"""WCAG 2.2 AA (SPEC 6, TASKS.md 6.5): axe-core finds no violation on the pages, in the light and the dark theme."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

AXE = Path(__file__).parents[3] / 'node_modules' / 'axe-core' / 'axe.min.js'
RULES = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
# The pages by the persona who sees them (None: not logged in)
PAGES = {
    None: ['/login'],
    'rainer': ['/setup'],
    'hans': ['/', '/week?week=2026-W44', '/month?month=2026-10', '/year?year=2026', '/review', '/settings', '/team',
             '/components'],
    'klara': ['/admin'],
}


def violations(page, path: str) -> list[str]:
    page.goto(path)
    page.wait_for_load_state('networkidle')
    page.add_script_tag(path=AXE)
    return page.evaluate(f'axe.run(document, {{ runOnly: {RULES} }}).then((result) => result.violations.map((v) => v.id))')


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_pages_meet_wcag_aa(browser, base, logged_in, theme):
    actual = {}
    for persona, paths in PAGES.items():
        page = logged_in(persona, theme) if persona else browser.new_page(base_url=base, color_scheme=theme)
        actual |= {path: violations(page, path) for path in paths}
    assert {path: found for path, found in actual.items() if found} == {}


def wider_than_the_window(page) -> list[str]:
    """The elements sticking out of the window, outside an area that scrolls by itself (none: the page reflows)."""
    return page.evaluate('''() => {
        const width = document.documentElement.clientWidth;
        const out = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > width + 1)
            .filter((e) => !e.closest('.table-scroll')).map((e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : ''));
        return document.documentElement.scrollWidth > width ? ['page', ...new Set(out)].slice(0, 6) : [];
    }''')


def test_pages_reflow_at_320_css_pixels(browser, base, logged_in):
    """WCAG 1.4.10 (1280 px at 400 %): no page scrolls sideways, and the pages meet AA at this width too, e.g. a table
    that scrolls by itself can be reached with the keyboard."""
    actual = {}
    for persona, paths in PAGES.items():
        page = logged_in(persona) if persona else browser.new_page(base_url=base)
        page.set_viewport_size({'width': 320, 'height': 640})
        actual |= {path: violations(page, path) + wider_than_the_window(page) for path in paths}
    assert {path: found for path, found in actual.items() if found} == {}


def test_the_week_editors_fit_a_narrow_screen(logged_in):
    """The forms in the week table stay within the screen, though the table itself scrolls sideways."""
    page = logged_in('hans')
    page.set_viewport_size({'width': 320, 'height': 640})
    page.goto('/week?week=2026-W44')
    actual = {}
    openers = {'.day-editor': '[aria-label="Edit Mon 26.10."]', '.entry-editor': '[data-opens="add-2026-10-26"]'}
    for editor, opener in openers.items():
        page.click(opener)
        box = page.locator(editor).bounding_box()
        actual[editor] = box['x'] >= 0 and box['x'] + box['width'] <= 320
        page.keyboard.press('Escape')
    assert actual == {'.day-editor': True, '.entry-editor': True}


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_the_entry_details_meet_wcag_aa_on_a_narrow_screen(logged_in, theme):
    page = logged_in('hans', theme)
    page.set_viewport_size({'width': 320, 'height': 640})
    page.goto('/review')
    page.click('#guessed button:has-text("Details")')
    page.locator('dialog .history-list').wait_for()
    page.add_script_tag(path=AXE)
    found = page.evaluate(f"axe.run(document.querySelector('dialog'), {{ runOnly: {RULES} }})"
                          '.then((result) => result.violations.map((v) => v.id))')
    assert found + wider_than_the_window(page) == []
