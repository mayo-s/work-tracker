import datetime as dt
import io
from decimal import Decimal

from src.lib.durations import parse_clock, parse_duration
from src.models.days import Day
from src.modules.importer.reconcile import DayDifference, reconcile
from src.modules.importer.run import import_rows
from src.modules.importer.sheet import parse_sheet
from src.modules.storage.days import DayRepository
from src.modules.storage.settings import load_settings, save_settings
from src.tests.users import USER

SHEET = '''Date,Start,End,Pause,Sum,Comment
 30.12.2024 Mon,08:00,16:00,,8:00,PTO
 31.12.2024 Tue,08:00,16:00,,8:00,PTO
 02.01.2025 Thu,08:00,16:00,,8:00,PTO
 06.01.2025 Mon,08:15,16:00,30,7:15,"4,0 AGA-39 refactor project structure"
 07.01.2025 Tue,07:30,16:00,30,8:00,
 08.01.2025 Wed,08:15,18:00,45,9:00,"8,0 AGA-39 adapt unittests"
 11.01.2025 Sat,08:00,16:00,,8:00,
 25.01.2025 Sat,08:00,16:00,,8:00,"4,0 Abreise LÜBECK"
'''


def sheet_rows(text):
    return list(parse_sheet(io.StringIO(text)))


def year_2025():
    header, *lines = SHEET.splitlines(keepends=True)
    return sheet_rows(header + ''.join(line for line in lines if '.2025 ' in line))


def test_imported_year_matches_sheet(conn):
    rows = year_2025()
    import_rows(conn, USER, rows)
    result = reconcile(conn, USER, rows, today=dt.date(2025, 1, 31))
    assert result.differences == ()
    # 06.01. −0:45, 08.01. +1:00, all other days 0:00
    assert result.sheet_overtime == result.app_overtime == parse_duration('0:15')


def test_balance_includes_earlier_years_and_counts_every_day(conn):
    save_settings(conn, USER, load_settings(conn, USER).model_copy(update={'balance_start': dt.date(2024, 12, 30)}))
    header, *lines = SHEET.splitlines(keepends=True)
    import_rows(conn, USER, sheet_rows(header + ''.join(lines[:2])))
    rows = year_2025()
    import_rows(conn, USER, rows)
    result = reconcile(conn, USER, rows, today=dt.date(2025, 1, 8))
    # 30.12. unpaid leave, 31.12. Silvester, 01.01. holiday, 02.01. PTO: 0:00 each;
    # 03.01. without record −8:00, 06.01. −0:45, 07.01. 0:00, 08.01. +1:00
    assert result.balance == -parse_duration('7:45')
    assert result.until == dt.date(2025, 1, 8)


def test_future_days_are_not_compared(conn):
    rows = year_2025()
    import_rows(conn, USER, rows)
    result = reconcile(conn, USER, rows, today=dt.date(2025, 1, 6))
    assert result.until == dt.date(2025, 1, 6)
    assert result.sheet_overtime == result.app_overtime


def test_changed_day_is_listed_as_difference(conn):
    rows = year_2025()
    import_rows(conn, USER, rows)
    shorter = Day(date=dt.date(2025, 1, 7), start=parse_clock('07:30'), end=parse_clock('15:00'), break_minutes=30)
    DayRepository(conn, USER).save(shorter)
    result = reconcile(conn, USER, rows, today=dt.date(2025, 1, 31))
    assert result.differences == (DayDifference(dt.date(2025, 1, 7), 0, -parse_duration('1:00'), ''),)
    assert '07.01.2025: sheet 0:00, app -1:00' in '\n'.join(result.lines())


def test_pto_account_of_the_year(conn):
    header, *lines = SHEET.splitlines(keepends=True)
    import_rows(conn, USER, sheet_rows(header + ''.join(lines[:2])))
    rows = year_2025()
    import_rows(conn, USER, rows)
    pto = reconcile(conn, USER, rows, today=dt.date(2025, 12, 31)).pto
    # 2024: 17.5 − 0.5 (Heiligabend) − 0.5 (Silvester); 30.12.2024 is unpaid leave
    # 2025: 1 (02.01.) + 0.5 (Heiligabend) + 0.5 (Silvester)
    assert (pto.year, pto.carried_over, pto.allowance, pto.used) == (2025, Decimal('16.5'), Decimal(31), Decimal(2))


def test_lines(conn):
    rows = year_2025()
    import_rows(conn, USER, rows)
    lines = reconcile(conn, USER, rows, today=dt.date(2025, 1, 31)).lines()
    assert lines[0] == 'Reconciliation 2025 (up to 31.01.2025)'
    assert lines[1].endswith('— no days differ')
    assert lines[-1].startswith('  PTO:')
