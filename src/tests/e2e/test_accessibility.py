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
