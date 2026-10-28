import pytest

from src.modules.importer.lines import split_hours


@pytest.mark.parametrize('line, expected', [
    ('1,5 KP-2035 refinement', (90, 'KP-2035 refinement')),
    ('0,75 KP-2044 attic extension mapping', (45, 'KP-2044 attic extension mapping')),
    ('8,0 PTO', (480, 'PTO')),
    ('2,0  #4159', (120, '#4159')),
    ('3,0', (180, '')),
    (' 4,0 PTO (afternoon) ', (240, 'PTO (afternoon)')),
    ('KP-2045 leasehold mapping', (None, 'KP-2045 leasehold mapping')),
    ('ICE 1,5 h delay', (None, 'ICE 1,5 h delay')),
    ('1. Weihnachtstag', (None, '1. Weihnachtstag')),
    ('80th anniversary', (None, '80th anniversary')),
    ('2025 retro', (None, '2025 retro')),
])
def test_split_hours(line, expected):
    assert split_hours(line) == expected
