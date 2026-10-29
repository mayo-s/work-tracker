"""The two palettes of main.css: every text color is readable on its backgrounds (WCAG AA, 4.5:1 for text)."""

import re

import pytest

from src.modules.pages.resources import STATIC_DIR

CSS = (STATIC_DIR / 'css' / 'main.css').read_text(encoding='utf-8')
TEXT_COLORS = ['text', 'muted', 'accent', 'warning-text', 'positive']


def colors(block_start):
    block = CSS[CSS.index(block_start):]
    block = block[:block.index('}')]
    return dict(re.findall(r'--color-([a-z-]+):\s*(#[0-9a-f]{6});', block))


LIGHT = colors(':root {')
DARK = colors(":root[data-theme='dark'] {")
SYSTEM_DARK = colors(":root:not([data-theme='light']) {")


def luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    lighter, darker = sorted([luminance(first), luminance(second)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_mode_defines_every_color_of_light_mode():
    assert set(DARK) == set(LIGHT)


def test_system_dark_mode_and_chosen_dark_mode_are_the_same():
    assert SYSTEM_DARK == DARK


@pytest.mark.parametrize('palette', [LIGHT, DARK], ids=['light', 'dark'])
@pytest.mark.parametrize('color', TEXT_COLORS)
def test_text_colors_are_readable_on_the_background(palette, color):
    assert contrast(palette[color], palette['background']) >= 4.5


@pytest.mark.parametrize('palette', [LIGHT, DARK], ids=['light', 'dark'])
@pytest.mark.parametrize('foreground, background', [
    *[(color, 'surface') for color in TEXT_COLORS],
    ('on-accent', 'accent'), ('accent', 'accent-light'), ('warning-text', 'warning-light'), ('positive', 'positive-light'),
    ('text', 'warning-light'),  # muted text in warning rows shows as text
])
def test_text_is_readable_on_surfaces_and_tints(palette, foreground, background):
    assert contrast(palette[foreground], palette[background]) >= 4.5
