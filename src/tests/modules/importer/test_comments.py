import pytest

from src.modules.importer.comments import ParsedEntry, parse_comment, parse_line


def entry(duration, source, ticket_key=None, activity=None, text='', coding=False):
    return ParsedEntry(duration, source, ticket_key, activity, text, coding)


@pytest.mark.parametrize('line, ticket, text', [
    ('4,0 KP-1951: data mapping', 'KP-1951', 'data mapping'),
    ('2,0 AGA-39 - connect to rds via aws_utils', 'AGA-39', 'connect to rds via aws_utils'),
    ('6,0 ENGINE-461', 'ENGINE-461', ''),
    ('1,0 MSI-3 setup', 'MSI-3', 'setup'),
    ('0,5 TNG-4908 PR and staging deployment', 'TNG-4908', 'PR and staging deployment'),
    ('3,0 KP-1893 Meeting/Planning: return value mapping', 'KP-1893', 'Meeting/Planning: return value mapping'),
])
def test_ticket_entry(line, ticket, text):
    [parsed] = parse_line(line)
    assert (parsed.ticket_key, parsed.text, parsed.coding, parsed.source) == (ticket, text, True, line)


def test_ticket_entry_duration():
    assert [parsed.duration for parsed in parse_line('0,75 KP-2044 attic extension mapping')] == [45]


@pytest.mark.parametrize('line, tickets, durations, text', [
    ('3,0 TNG-5213, TNG-5214', ['TNG-5213', 'TNG-5214'], [90, 90], ''),
    ('1,5 ENGINE-592/ENGINE-593 credentials', ['ENGINE-592', 'ENGINE-593'], [45, 45], 'credentials'),
    ('1,5 KP-2035, KP-2044, KP-2045, KP-2053 Refinement', ['KP-2035', 'KP-2044', 'KP-2045', 'KP-2053'], [30, 30, 15, 15],
     'Refinement'),
    ('1,0 PR AGA-39 and AGA-40 (merge AGA-39)', ['AGA-39', 'AGA-40'], [30, 30], 'PR AGA-39 and AGA-40 (merge AGA-39)'),
    ('8,0 MSI-3, MSI-4, MSI-5, MSI-6', ['MSI-3', 'MSI-4', 'MSI-5', 'MSI-6'], [120, 120, 120, 120], ''),
])
def test_several_tickets_split_evenly(line, tickets, durations, text):
    parsed = parse_line(line)
    assert [entry.ticket_key for entry in parsed] == tickets
    assert [entry.duration for entry in parsed] == durations
    assert {entry.text for entry in parsed} == {text}


@pytest.mark.parametrize('line, duration, text', [
    ('2,0 PR review', 120, 'PR review'),
    ('6,0 PR reviews zipkin lib', 360, 'PR reviews zipkin lib'),
    ('3,0 PR lead-notification-service', 180, 'PR lead-notification-service'),
    ('1,0 PR leadmanagement zipkin lib', 60, 'PR leadmanagement zipkin lib'),
])
def test_pr_review_without_ticket(line, duration, text):
    assert parse_line(line) == [entry(duration, line, text=text, coding=True)]


@pytest.mark.parametrize('line, activity, text', [
    ('0,5 Meeting: Frank, Intro to process', 'Meeting', 'Frank, Intro to process'),
    ('4,0 Meeting(s): discuss possible optimizations', 'Meeting', 'discuss possible optimizations'),
    ('1,0 Meeting: TNG-4517, TNG-4528 testing mit Tim', 'Meeting', 'TNG-4517, TNG-4528 testing mit Tim'),
    ('2,0 Tool Management', 'Tool Management', ''),
    ('2,0 TM', 'Tool Management', ''),
    ('1,5 Tool Management (TM)', 'Tool Management', ''),
    ('1,0 Tool Management(TM)', 'Tool Management', ''),
    ('1,0 GCC (Tool Management)', 'Tool Management', ''),
    ('1,5 Tool Management (GCC Tactical and Governance)', 'Tool Management', 'GCC Tactical and Governance'),
    ('4,0 Anreise LÜBECK', 'Travel', 'Anreise LÜBECK'),
    ('3,5 ABREISE Lübeck', 'Travel', 'ABREISE Lübeck'),
    ('2,0 Anfahrt/Abfahrt MyB - Rückgabe MacBook', 'Travel', 'Anfahrt/Abfahrt MyB - Rückgabe MacBook'),
    ('6,0 Hackathon "Picard" (a tng agent) - restructure', 'Other', 'Hackathon "Picard" (a tng agent) - restructure'),
    ('1,5 Tactical Meeting', 'Meeting', 'Tactical Meeting'),
    ('1,25 Teamstufe Meeting (recruiting)', 'Meeting', 'Teamstufe Meeting (recruiting)'),
    ('6,0 Meetings und Absprachen', 'Meeting', 'Meetings und Absprachen'),
    ('0,5 Standup', 'Meeting', 'Standup'),
    ('1,0 Retro', 'Meeting', 'Retro'),
    ('2,0 Retrospective', 'Meeting', 'Retrospective'),
    ('1,0 Planning', 'Meeting', 'Planning'),
    ('6,0 Incident - Teams - Cannot bypass meeting lobby', 'Other', 'Incident - Teams - Cannot bypass meeting lobby'),
    ('1,0 Retrofit tests', 'Other', 'Retrofit tests'),
    ('3,0', 'Other', ''),
])
def test_activity_entry(line, activity, text):
    [parsed] = parse_line(line)
    assert (parsed.activity, parsed.text, parsed.ticket_key, parsed.coding) == (activity, text, None, False)


@pytest.mark.parametrize('line, tickets', [
    ('KP-2045 leasehold mapping', ['KP-2045']),
    ('ENGINE-598', ['ENGINE-598']),
    ('ENGINE-592 ENGINE-593 credentials', ['ENGINE-592', 'ENGINE-593']),
])
def test_ticket_without_hours_is_zero_entry(line, tickets):
    parsed = parse_line(line)
    assert [(entry.ticket_key, entry.duration) for entry in parsed] == [(key, 0) for key in tickets]


@pytest.mark.parametrize('line', [
    'Anreise LÜBECK',
    'Meeting: plan Authorizer, create new Board/Project',
    'ICE 1,5 h delay',
    '- tng exchange',
    'O365 integration - no tickets, no permissions',
])
def test_note_lines(line):
    assert parse_line(line) == []


def test_parse_comment_separates_entries_and_notes():
    parsed = parse_comment(['Anreise LÜBECK', '3,0 KP-2058', '2,0 Meeting: TM und KI Koordination', 'ICE 1,5 h delay'])
    assert [(entry.ticket_key, entry.activity) for entry in parsed.entries] == [('KP-2058', None), (None, 'Meeting')]
    assert parsed.notes == ('Anreise LÜBECK', 'ICE 1,5 h delay')


@pytest.mark.parametrize('line, tickets, text', [
    ('1,5 #KP-1494 Discuss solution', ['KP-1494'], 'Discuss solution'),
    ('2,0 TNG TNG-4828, TNG-4840', ['TNG-4828', 'TNG-4840'], ''),
    ('6,0 EINGINE-461', ['ENGINE-461'], ''),
    ('4,0 MSI-02 basic project setup', ['MSI-2'], 'basic project setup'),
])
def test_corrected_tickets_are_not_flagged(line, tickets, text):
    parsed = parse_line(line)
    expected = [(key, text, False) for key in tickets]
    assert [(entry.ticket_key, entry.text, entry.uncertain_ticket) for entry in parsed] == expected


@pytest.mark.parametrize('line, tickets, durations, text', [
    ('6,0 #4138, #4139 create meeting service', ['TNG-4138', 'TNG-4139'], [180, 180], 'create meeting service'),
    ('3,0 #1482 fix tests, add new tests', ['KP-1482'], [180], 'fix tests, add new tests'),
    ('3,0 #4347 aka #1482 add impersonation', ['TNG-4347'], [180], 'add impersonation (aka KP-1482)'),
    ('2,0 #4347/#1482 Logging', ['TNG-4347'], [120], 'Logging (aka KP-1482)'),
    ('1,0 TNG-2035ff PR and deployment', ['TNG-2035'], [60], 'PR and deployment'),
])
def test_guessed_tickets_are_flagged(line, tickets, durations, text):
    parsed = parse_line(line)
    assert [entry.ticket_key for entry in parsed] == tickets
    assert [entry.duration for entry in parsed] == durations
    assert {(entry.text, entry.uncertain_ticket, entry.source) for entry in parsed} == {(text, True, line)}


def test_bare_number_without_hours_is_flagged_zero_entry():
    [parsed] = parse_line('#4250 check results')
    assert (parsed.ticket_key, parsed.duration, parsed.uncertain_ticket) == ('TNG-4250', 0, True)
