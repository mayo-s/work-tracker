import datetime as dt
import io

import pytest

from src.lib.durations import parse_clock, parse_duration
from src.modules.importer.sheet import SheetFormatError, SheetRow, parse_sheet, read_sheet

HEADER = 'Date,Start,End,Pause,Sum,Comment\n'


def parse(text):
    return list(parse_sheet(io.StringIO(HEADER + text)))


def test_work_day_with_comment_lines():
    [row] = parse(' 09.01.2026 Fri,07:30,16:00,30,8:00,"3,0 KP-1951: data mapping\n1,0 PR review (zipkin lib)"\n')
    assert row == SheetRow(
        date=dt.date(2026, 1, 9),
        start=parse_clock('07:30'),
        end=parse_clock('16:00'),
        pause=30,
        total=parse_duration('8:00'),
        comment=('3,0 KP-1951: data mapping', '1,0 PR review (zipkin lib)'),
    )


def test_comment_lines_are_stripped_and_empty_lines_dropped():
    [row] = parse(' 21.10.2026 Wed,08:15,18:00,45,9:00,"1,0 Missing teams_calls access\n\nENGINE-598 \nENGINE-597"\n')
    assert row.comment == ('1,0 Missing teams_calls access', 'ENGINE-598', 'ENGINE-597')


def test_quoted_quotes_in_comment():
    [row] = parse(' 19.03.2026 Thu,08:15,18:00,30,9:15,"6,0 Hackathon ""Picard"" (a tng agent) - restructure"\n')
    assert row.comment == ('6,0 Hackathon "Picard" (a tng agent) - restructure',)


@pytest.mark.parametrize('pause, expected', [('', None), ('0', 0), ('180', 180)])
def test_pause(pause, expected):
    [row] = parse(f' 12.02.2026 Thu,08:30,20:00,{pause},8:30,\n')
    assert row.pause == expected


def test_empty_future_day():
    [row] = parse(' 28.10.2026 Wed,,,,0:00,\n')
    assert (row.start, row.end, row.pause, row.total, row.comment) == (None, None, None, 0, ())
    assert row.is_empty


def test_future_day_with_comment_is_not_empty():
    [row] = parse(' 24.12.2026 Thu,,,,0:00,Heiligabend\n')
    assert not row.is_empty


@pytest.mark.parametrize('line, placeholder', [
    (' 03.01.2026 Sat,08:00,16:00,,8:00,\n', True),
    (' 01.06.2024 Sat,08:00,16:00,0,8:00,First Day at Dr. Klein\n', True),
    (' 30.05.2025 Fri,08:00,16:00,480,0:00,PTO\n', False),
    (' 06.12.2025 Sat,08:00,19:30,,11:30,"3,5 ABREISE Lübeck"\n', False),
    (' 06.01.2026 Tue,07:30,16:00,30,8:00,\n', False),
])
def test_placeholder_times(line, placeholder):
    [row] = parse(line)
    assert row.has_placeholder_times is placeholder


def test_several_rows_with_umlauts(tmp_path):
    path = tmp_path / 'sheet.csv'
    path.write_text(
        '﻿' + HEADER + ' 10.03.2026 Tue,07:30,16:00,30,8:00,"Anreise LÜBECK\n3,0 KP-2058"\n'
        ' 11.03.2026 Wed,08:30,17:30,30,8:30,OFFICE DAY\n',
        encoding='utf-8',
    )
    rows = read_sheet(path)
    assert [row.date for row in rows] == [dt.date(2026, 3, 10), dt.date(2026, 3, 11)]
    assert rows[0].comment == ('Anreise LÜBECK', '3,0 KP-2058')


def test_rejects_unexpected_header():
    lines = io.StringIO('Datum,Start,Ende,Pause,Summe,Kommentar\n')
    with pytest.raises(SheetFormatError):
        list(parse_sheet(lines))


@pytest.mark.parametrize('line', [
    ' 09.01.2026 Mon,07:30,16:00,30,8:00,\n',
    ' 32.01.2026 Fri,07:30,16:00,30,8:00,\n',
    ' 09.01.2026 Fri,7.30,16:00,30,8:00,\n',
    ' 09.01.2026 Fri,07:30,16:00,halb,8:00,\n',
    ' 09.01.2026 Fri,07:30,16:00,30,8,\n',
    ' 09.01.2026 Fri,07:30,16:00,30\n',
])
def test_rejects_invalid_row(line):
    lines = io.StringIO(HEADER + line)
    with pytest.raises(SheetFormatError):
        list(parse_sheet(lines))
