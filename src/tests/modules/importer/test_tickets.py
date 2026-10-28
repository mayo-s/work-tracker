import pytest

from src.modules.importer.tickets import CleanedText, bare_key, clean_tickets, find_tickets


@pytest.mark.parametrize('text, cleaned', [
    ('EINGINE-461', 'ENGINE-461'),
    ('#KP-1494 Discuss solution', 'KP-1494 Discuss solution'),
    ('TNG TNG-4828, TNG-4840', 'TNG-4828, TNG-4840'),
    ('TNG 5212 refactor routes', 'TNG-5212 refactor routes'),
    ('TNG4840 contacts', 'TNG-4840 contacts'),
    ('KP-1891, KP1895 prepare PR', 'KP-1891, KP-1895 prepare PR'),
    ('MSI-02 basic project setup', 'MSI-2 basic project setup'),
])
def test_obvious_typos_are_corrected_without_flag(text, cleaned):
    assert clean_tickets(text) == CleanedText(cleaned)


@pytest.mark.parametrize('text, cleaned', [
    ('#4138, #4139 create meeting service', 'TNG-4138, TNG-4139 create meeting service'),
    ('# 4251 refine needed information', 'TNG-4251 refine needed information'),
    ('#1482 fix tests', 'KP-1482 fix tests'),
    ('TNG-2035ff PR and deployment', 'TNG-2035 PR and deployment'),
])
def test_guessed_keys_are_flagged(text, cleaned):
    assert clean_tickets(text) == CleanedText(cleaned, uncertain=True)


@pytest.mark.parametrize('text, cleaned', [
    ('#4347 aka #1482 add impersonation', 'TNG-4347 add impersonation'),
    ('#4347/#1482 adapt tests', 'TNG-4347 adapt tests'),
])
def test_alias_keeps_first_key_and_remembers_second(text, cleaned):
    assert clean_tickets(text) == CleanedText(cleaned, uncertain=True, aliases=('KP-1482',))


@pytest.mark.parametrize('text', [
    'ENGINE-592/ENGINE-593 credentials',
    'KP/TNG Know How Exchange',
    'TNG event time stamps (offset mismatch)',
    'TNG random 500 when creating events',
    'O365 message filter',
    'IT Infrastructure outage ()',
])
def test_text_without_typos_stays(text):
    assert clean_tickets(text) == CleanedText(text)


@pytest.mark.parametrize('number, key', [('4138', 'TNG-4138'), ('4000', 'TNG-4000'), ('3999', 'KP-3999'), ('1482', 'KP-1482')])
def test_bare_key(number, key):
    assert bare_key(number) == key


def test_find_tickets_distinct_in_order():
    assert find_tickets('PR AGA-39 and AGA-40 (merge AGA-39), see KP-2035') == ['AGA-39', 'AGA-40', 'KP-2035']
