import datetime as dt
import io

import pytest

from src.lib.daytypes import DayType
from src.models.history import HistoryAction
from src.models.review import FlagReason
from src.modules.importer.__main__ import main
from src.modules.importer.run import SheetImportError, import_rows
from src.modules.importer.sheet import parse_sheet
from src.modules.storage.catalog import ActivityTypeRepository
from src.modules.storage.database import Database
from src.modules.storage.days import DayRepository
from src.modules.storage.entries import EntryRepository
from src.modules.storage.errors import ConflictError
from src.modules.storage.tickets import TicketRepository

NOW = dt.datetime(2026, 10, 28, 16, 0)
SHEET = '''Date,Start,End,Pause,Sum,Comment
 03.03.2026 Tue,07:00,15:30,30,8:00,"1,0 KP-2039 refinement and implementation
1,5 KP-2035, KP-2044, KP-2045, KP-2053 Refinement
2,0 Meeting: Stages for AWS Lambdas"
 04.03.2026 Wed,08:15,18:00,30,9:15,"Anreise LÜBECK
2,0 EINGINE-461"
 05.03.2026 Thu,08:00,16:00,,8:00,PTO
 07.03.2026 Sat,08:00,16:00,,8:00,
 08.03.2026 Sun,08:00,19:30,,11:30,"3,5 ABREISE Lübeck"
 09.03.2026 Mon,07:30,16:30,30,8:30,"1,0 TNG-2035ff PR and deployment
2,0 PR review (zipkin lib)
KP-2045 leasehold mapping"
 10.03.2026 Tue,,,,0:00,
'''


def rows(text=SHEET):
    return list(parse_sheet(io.StringIO(text)))


def run(conn, sheet=SHEET, replace=False):
    return import_rows(conn, rows(sheet), replace, clock=lambda: NOW)


def test_days_with_times_types_and_notes(conn):
    run(conn)
    days = DayRepository(conn)
    assert days.get(dt.date(2026, 3, 3)).worked == 8 * 60
    assert days.get(dt.date(2026, 3, 4)).note == 'Anreise LÜBECK'
    assert days.get(dt.date(2026, 3, 5)).day_type is DayType.PTO
    assert days.get(dt.date(2026, 3, 8)).worked == 3 * 60 + 30


def test_blank_days_are_not_stored(conn):
    run(conn)
    days = DayRepository(conn)
    assert days.get(dt.date(2026, 3, 7)) is None
    assert days.get(dt.date(2026, 3, 10)) is None


def test_entries_with_history_of_the_original_line(conn):
    run(conn)
    entries = EntryRepository(conn)
    first_day = entries.between(dt.date(2026, 3, 3), dt.date(2026, 3, 3))
    assert [(entry.kind, entry.duration) for entry in first_day] == [
        ('ticket', 60), ('ticket', 30), ('ticket', 30), ('ticket', 15), ('ticket', 15), ('activity', 120),
    ]
    [change] = entries.history(first_day[1].id)
    assert (change.action, change.detail) == (HistoryAction.IMPORTED, '1,5 KP-2035, KP-2044, KP-2045, KP-2053 Refinement')


def test_activity_entries_reference_activity_types(conn):
    run(conn)
    meeting = next(activity for activity in ActivityTypeRepository(conn).all() if activity.name == 'Meeting')
    first_day = EntryRepository(conn).between(dt.date(2026, 3, 3), dt.date(2026, 3, 3))
    [entry] = [entry for entry in first_day if entry.kind == 'activity']
    assert (entry.activity_type_id, entry.note) == (meeting.id, 'Stages for AWS Lambdas')


def test_tickets_are_created_without_service(conn):
    run(conn)
    assert TicketRepository(conn).get('ENGINE-461').service_id is None


def test_flags_for_review(conn):
    run(conn)
    entries, days = EntryRepository(conn), DayRepository(conn)
    [entry_flag] = entries.entry_flags()
    assert (entry_flag.reason, entry_flag.detail) == (FlagReason.UNCERTAIN_TICKET, '1,0 TNG-2035ff PR and deployment')
    assert entries.get(entry_flag.entry_id).ticket_key == 'TNG-2035'
    assert [(flag.date, flag.reason) for flag in days.day_flags()] == [(dt.date(2026, 3, 8), FlagReason.WEEKEND_HOURS)]


def test_summary(conn):
    summary = run(conn)
    assert summary.year == 2026
    assert not summary.replaced
    assert summary.days == {DayType.WORK: 4, DayType.PTO: 1}
    assert dict(summary.entries) == {'ticket': 9, 'activity': 2, 'zero': 1, 'no ticket': 1}
    assert (summary.corrected_tickets, summary.unpaid_leave) == (1, 0)
    assert (summary.flagged_entries, summary.flagged_days) == (1, 1)
    assert summary.lines()[0] == 'Imported 2026'


def test_unpaid_leave_correction(conn):
    summary = run(conn, 'Date,Start,End,Pause,Sum,Comment\n 08.08.2024 Thu,08:00,16:00,0,8:00,PTO\n')
    assert DayRepository(conn).get(dt.date(2024, 8, 8)).day_type is DayType.UNPAID_LEAVE
    assert summary.unpaid_leave == 1


def test_second_import_is_refused(conn):
    run(conn)
    sheet = rows()
    with pytest.raises(ConflictError):
        import_rows(conn, sheet)


def test_replace_imports_again_and_keeps_ticket_services(conn):
    run(conn)
    tickets = TicketRepository(conn)
    tickets.set_service('KP-2039', 3)
    old_ids = {entry.id for entry in EntryRepository(conn).between(dt.date(2026, 1, 1), dt.date(2026, 12, 31))}
    summary = run(conn, replace=True)
    entries = EntryRepository(conn)
    new = entries.between(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert summary.replaced
    assert len(new) == 11
    assert old_ids.isdisjoint(entry.id for entry in new)
    assert all(entries.history(entry_id) == [] for entry_id in old_ids)
    assert len(entries.entry_flags()) == 1
    assert tickets.get('KP-2039').service_id == 3


def test_replace_keeps_other_years(conn):
    run(conn)
    run(conn, 'Date,Start,End,Pause,Sum,Comment\n 08.08.2024 Thu,08:00,16:00,0,8:00,PTO\n', replace=True)
    assert DayRepository(conn).get(dt.date(2026, 3, 5)) is not None


@pytest.mark.parametrize('sheet', [
    'Date,Start,End,Pause,Sum,Comment\n',
    'Date,Start,End,Pause,Sum,Comment\n 31.12.2025 Wed,,,,0:00,PTO\n 01.01.2026 Thu,,,,0:00,\n',
])
def test_sheet_must_hold_one_year(conn, sheet):
    sheet_rows = rows(sheet)
    with pytest.raises(SheetImportError):
        import_rows(conn, sheet_rows)


def test_invalid_duration_names_the_line(conn):
    sheet_rows = rows('Date,Start,End,Pause,Sum,Comment\n 09.03.2026 Mon,07:30,16:30,30,8:30,"0,1 TNG-5214"\n')
    with pytest.raises(SheetImportError, match="'0,1 TNG-5214'"):
        import_rows(conn, sheet_rows)


def test_command_line(tmp_path, capsys):
    sheet, db_path = tmp_path / 'sheet.csv', tmp_path / 'cli.db'
    sheet.write_text(SHEET, encoding='utf-8')
    assert main([str(sheet), '--db', str(db_path)]) == 0
    assert 'Imported 2026' in capsys.readouterr().out
    assert main([str(sheet), '--db', str(db_path)]) == 1
    assert 'nothing was written' in capsys.readouterr().err
    assert main([str(sheet), '--db', str(db_path), '--replace']) == 0
    with Database(db_path).transaction() as conn:
        assert len(EntryRepository(conn).between(dt.date(2026, 1, 1), dt.date(2026, 12, 31))) == 11


def test_command_line_rolls_back_failed_import(tmp_path):
    sheet, db_path = tmp_path / 'sheet.csv', tmp_path / 'cli.db'
    sheet.write_text(SHEET.replace('"3,5 ABREISE Lübeck"', '"0,1 ABREISE Lübeck"'), encoding='utf-8')
    assert main([str(sheet), '--db', str(db_path)]) == 1
    with Database(db_path).transaction() as conn:
        assert DayRepository(conn).get(dt.date(2026, 3, 3)) is None
