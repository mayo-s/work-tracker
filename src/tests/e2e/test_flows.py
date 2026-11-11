"""The main flows in the browser, one per page that changes data, as a user goes through them."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from src.tests.e2e.conftest import code
from src.tests.users import PASSWORD

pytestmark = pytest.mark.e2e


def test_root_and_admins_log_in_with_their_code(browser, base):
    page = browser.new_page(base_url=base)
    page.goto('/login')
    page.fill('#login-name', 'klara')
    page.fill('#login-password', PASSWORD)
    page.click('button:has-text("Log in")')
    page.fill('#login-code', code())
    page.click('button:has-text("Log in")')
    expect(page).to_have_url(f'{base}/')
    expect(page.locator('.account-links a[href="/admin"]')).to_have_count(1)  # in the menu


def test_a_new_user_is_set_up(logged_in):
    page = logged_in('rainer')
    page.goto('/week')
    expect(page).to_have_url(re.compile('/setup$'))
    for _ in range(4):
        page.click('button:has-text("Next")')
    expect(page.locator('.setup-summary')).to_contain_text('40:00 h per week, Mon, Tue, Wed, Thu, Fri')
    page.click('button:has-text("Start")')
    expect(page).to_have_url(re.compile('/$'))
    expect(page.locator('#dashboard')).to_contain_text('Balance')


def test_record_a_day_then_add_and_change_an_entry(logged_in):
    page = logged_in('hans')
    page.goto('/week?week=2026-W44')
    page.click('[aria-label="Edit Mon 26.10."]')
    page.fill('#day-start', '08:00')
    page.fill('#day-end', '16:30')
    page.click('.day-editor button:has-text("Save")')
    expect(page.locator('.week-table')).to_contain_text('08:00–16:30')
    page.click('[data-opens="add-2026-10-26"]')
    page.fill('#entry-duration', '1.5')
    page.fill('#entry-ticket_key', 'tng-5882')
    page.click('.entry-editor button:has-text("Save")')
    entry = page.locator('.entry', has_text='TNG-5882')
    expect(entry).to_contain_text('1:30')
    entry.locator('button:has-text("Edit")').click()
    page.fill('#entry-duration', '2h')
    page.click('.entry-editor button:has-text("Save")')
    expect(page.locator('.entry', has_text='TNG-5882')).to_contain_text('2:00')


def test_on_phones_the_week_is_a_card_per_day(logged_in):
    page = logged_in('hans')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('/week?week=2026-W44')
    card = page.locator('.day-card', has=page.locator('h2', has_text='Mon 26.10.'))
    page.click('[aria-label="Edit Mon 26.10."]')
    page.fill('#day-start', '08:00')
    page.fill('#day-end', '16:30')
    page.click('.day-editor button:has-text("Save")')
    expect(card.locator('.day-card-line')).to_have_text(['Times 08:00–16:30 Break 0:30 legal',
                                                         'Worked 8:00 Target 8:00 Overtime 0:00'])
    card.locator('button:has-text("+ Add entry")').click()
    page.fill('#entry-duration', '1.5')
    page.fill('#entry-ticket_key', 'tng-5882')
    page.click('.entry-editor button:has-text("Save")')
    expect(card.locator('.entry', has_text='TNG-5882')).to_contain_text('1:30')
    assert page.evaluate('document.documentElement.scrollWidth') == 390  # nothing scrolls sideways
    page.set_viewport_size({'width': 1280, 'height': 900})
    expect(page.locator('.week-table')).to_contain_text('08:00–16:30')  # the table again on a wider screen


def test_on_phones_list_tables_are_blocks_of_label_and_value(logged_in):
    page = logged_in('hans')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('/team')
    klara = page.locator('#members tbody tr', has_text='klara')
    expect(klara.locator('td[data-label="Member since"]')).to_be_visible()
    expect(page.locator('#members thead')).to_have_css('position', 'absolute')  # for screen readers only
    page.goto('/review')
    ticket = page.locator('#tickets tbody tr', has_text='TNG-4347')
    expect(ticket.locator('td[data-label="Entries"]')).to_have_text('1')
    page.fill('#tickets .review-toolbar input[type="search"]', 'other')
    expect(ticket).to_be_hidden()  # filtered out, though rows are blocks
    assert page.evaluate('document.documentElement.scrollWidth') == 390


def test_start_and_end_now_on_today(logged_in):
    page = logged_in('hans')
    page.clock.set_fixed_time('2026-10-28T08:12:00')
    page.goto('/week?week=2026-W44')
    page.click('button:has-text("Start now")')
    row = page.locator('tr', has=page.locator('[aria-label="Edit Wed 28.10."]'))
    expect(row).to_contain_text('08:12– best 16:42')
    expect(row).to_contain_text('-8:00')
    expect(page.locator('button:has-text("Start now")')).to_have_count(0)
    page.click('[aria-label="Edit Wed 28.10."]')
    expect(page.locator('#day-end')).to_have_attribute('placeholder', '16:42')
    expect(page.locator('button:has-text("End now")')).to_have_count(0)  # saving would close the form
    page.click('.day-editor button:has-text("Cancel")')
    page.clock.set_fixed_time('2026-10-28T16:50:00')
    page.click('button:has-text("End now")')
    expect(row).to_contain_text('08:12–16:50')
    expect(row).to_contain_text('+0:08')
    expect(page.locator('button:has-text("End now")')).to_have_count(0)


def test_choose_an_activity_type_rename_the_ticket_and_assign_a_service(logged_in):
    page = logged_in('hans')
    page.goto('/review')
    badge = page.locator('.app-nav a[href="/review"] .badge')
    expect(badge).to_have_text('2')  # the entry without activity type and its ticket without service
    page.click('#activity-types button:has-text("Details")')
    dialog = page.locator('dialog')
    expect(dialog.locator('h3')).to_have_text('Mon 26.10.2026 · no times')
    dialog.locator('button:has-text("Close")').click()
    expect(dialog).to_have_count(0)
    page.check('#activity-types input[aria-label="Select all shown entries"]')
    page.select_option('#activity-types select', label='Coding')
    page.click('#activity-types button:has-text("Assign to 1 selected")')
    expect(page.locator('#review-status')).to_have_text('Coding assigned to 1 entry')
    page.locator('#tickets tr', has_text='TNG-4347').locator('button:has-text("Rename")').click()
    page.fill('#tickets .rename-input', 'kp-1483')
    page.click('#tickets .rename-form button:has-text("Rename")')
    expect(page.locator('#review-status')).to_have_text('TNG-4347 renamed to KP-1483 (1 entry)')
    page.check('#tickets input[aria-label="Select all shown tickets"]')
    page.click('#tickets button:has-text("Assign to 1 selected")')
    expect(page.locator('#review-status')).to_contain_text('assigned to 1 ticket')
    expect(badge).to_have_count(0)


def test_add_and_delete_a_service(logged_in):
    page = logged_in('hans')
    page.goto('/settings')
    services = page.locator('#services')
    services.get_by_label('Short name').fill('IAM')
    services.locator('button:has-text("Add service")').click()
    row = page.locator('#services tr', has_text='IAM')
    expect(row).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    row.locator('button:has-text("Delete")').click()
    expect(page.locator('#services tr', has_text='IAM')).to_have_count(0)


def test_an_admin_sets_a_one_time_password(logged_in):
    page = logged_in('klara')
    page.goto('/admin')
    page.fill('#otp-email', 'hans.dampf@example.com')
    page.click('#one-time-password button:has-text("Set one-time password")')
    dialog = page.locator('dialog')
    expect(dialog).to_contain_text('One-time password for hans')
    dialog.locator('button:has-text("Set one-time password")').click()
    expect(page.locator('dialog .one-time-password')).to_have_text(re.compile(r'\S{12,}'))
    page.click('dialog button:has-text("Done")')
    expect(page.locator('body')).to_contain_text('Set a one-time password for hans')


def test_an_admin_deletes_a_deactivated_user_after_typing_the_username(logged_in):
    page = logged_in('klara')
    page.goto('/admin')
    page.once('dialog', lambda dialog: dialog.accept())  # "Deactivate rainer?"
    page.get_by_label('Status of rainer').select_option('deactivated')
    page.get_by_role('button', name='Delete rainer').click()
    dialog = page.locator('dialog')
    expect(dialog.locator('h2')).to_have_text('Delete rainer')
    dialog.get_by_label('Type rainer to confirm').fill('rainer')
    dialog.locator('button:has-text("Delete account")').click()
    expect(page.locator('body')).to_contain_text('Deleted rainer')
    expect(page.locator('#users tr', has_text='rainer.zufall@example.com')).to_have_count(0)


def test_a_user_deletes_their_own_account_in_the_settings(logged_in):
    page = logged_in('hans')
    page.goto('/settings#delete-account')
    page.fill('#delete-account-password', PASSWORD)
    page.click('button:has-text("Delete my account")')
    page.locator('dialog button:has-text("Delete my account")').click()
    expect(page).to_have_url(re.compile(r'/login\?deleted$'))
    expect(page.get_by_role('status')).to_have_text('Your account and all its data are deleted.')


def test_a_team_admin_views_a_member_read_only(logged_in, people):
    page = logged_in('hans')
    page.goto('/')
    page.select_option('#dashboard-member', label='Klara Himmel')
    page.click('.member-chooser button:has-text("Show")')
    expect(page).to_have_url(re.compile(f'member={people["klara"]}'))
    expect(page.locator('body')).to_contain_text('Klara Himmel')
    page.click('.app-nav a:has-text("Week")')
    expect(page).to_have_url(re.compile(f'/week\\?member={people["klara"]}'))
    expect(page.locator('.week-table')).to_be_visible()
    expect(page.locator('.week-table button:has-text("Edit")')).to_have_count(0)
    page.fill('#week-go-date', '2026-03-04')
    page.click('#week-go button:has-text("Go")')
    expect(page).to_have_url(re.compile(f'/week\\?week=2026-W10&member={people["klara"]}'))
    expect(page.locator('#week-title')).to_have_text('Week 10 · 2026')


def test_a_team_admin_opens_the_team_report(logged_in):
    page = logged_in('hans')
    page.goto('/')
    page.click('.app-nav a:has-text("Audit")')
    expect(page).to_have_url(re.compile(r'/team/report$'))
    expect(page.locator('.app-nav a:has-text("Audit")')).to_have_attribute('aria-current', 'page')
    report = page.locator('#team-report')
    expect(report).to_contain_text('Platform')
    expect(report.locator('.report-cards .card h3')).to_have_text(['Hans Dampf', 'Klara Himmel'])
    expect(report).to_contain_text('Current members only')
    with page.expect_download() as download:
        page.locator('#team-report-exports a:has-text("Export CSV")').click()
    assert re.fullmatch(r'\d{8}_\d{4}_team_report_Platform\.csv', download.value.suggested_filename)
    assert 'Member;Klara Himmel;Worked;' in Path(download.value.path()).read_text(encoding='utf-8-sig')
    page.evaluate('window.print = () => { window.printedAs = document.title; dispatchEvent(new Event("afterprint")); }')
    page.locator('#team-report-exports button:has-text("Save as PDF")').click()
    assert re.fullmatch(r'\d{8}_\d{4}_team_report_Platform', page.evaluate('window.printedAs'))
    expect(page).to_have_title('Team report · Work Tracker')
    page.emulate_media(media='print')  # light, without navigation and buttons, though the browser is dark
    expect(page.locator('.app-header')).to_be_hidden()
    expect(page.locator('.report-exports')).to_be_hidden()
    expect(page.locator('.report-open').first).to_be_hidden()
    assert page.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(255, 255, 255)'
    page.emulate_media(media='screen')
    page.click('#team-report-kind')
    expect(page).to_have_url(re.compile(r'&year=\d{4}'))
    expect(page.locator('#team-report-current')).to_have_text('Current year')
    report.locator('a.report-member', has_text='Klara Himmel').click()
    expect(page).to_have_url(re.compile(r'/year\?year=\d{4}&member='))
    expect(page.locator('.team-view-banner')).to_contain_text("Klara Himmel's data")
    expect(page.locator('.app-nav a:not([href="/review"])')).to_have_text(
        ['Dashboard', 'Week', 'Month', 'Year', 'Audit'])
    page.click('.team-view-banner a:has-text("Back to the team report")')
    expect(page).to_have_url(re.compile(r'/team/report\?team=.+&year=\d{4}'))
    report.locator('a.report-member', has_text='Hans Dampf').click()  # the own card
    expect(page).to_have_url(re.compile(r'/year\?year=\d{4}$'))
    expect(page.locator('.team-view-banner')).to_have_count(0)


@pytest.mark.parametrize('persona, tabs, menu', [
    ('hans', ['Dashboard', 'Week', 'Month', 'Year', 'Audit'], ['Team', 'Settings', 'Log out']),  # team admin
    ('klara', ['Dashboard', 'Week', 'Month', 'Year'], ['Support', 'Settings', 'Admin', 'Log out']),  # admin, support
    ('pascal', [], ['Settings', 'Admin', 'Log out']),  # root
])
def test_the_tabs_and_the_menu_in_their_order(logged_in, persona, tabs, menu):
    page = logged_in(persona)
    page.goto('/settings')
    expect(page.locator('.app-nav a:not([href="/review"])')).to_have_text(tabs)  # Review comes and goes with its items
    expect(page.locator('.account-links > *')).to_have_text(menu)


# The right end of the header: the search field, the name, the dark mode switch, the menu
HEADER_END = [re.compile('nav-search'), 'muted', re.compile('theme-toggle'), 'account-menu']


def test_the_menu_opens_below_its_button_and_closes(logged_in):
    page = logged_in('hans')
    page.goto('/week')
    toggle = page.locator('.account-toggle')
    links = page.locator('.account-links')
    expect(page.locator('.app-user > *')).to_have_class(HEADER_END)
    expect(links).to_be_hidden()
    toggle.click()
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    links.locator('a:has-text("Settings")').focus()
    page.keyboard.press('Escape')
    expect(links).to_be_hidden()
    expect(toggle).to_be_focused()
    toggle.click()
    page.click('h1')  # outside
    expect(links).to_be_hidden()
    toggle.click()
    links.locator('a:has-text("Team")').click()
    expect(page).to_have_url(re.compile('/team$'))
    page.click('.account-toggle')
    expect(page.locator('.account-links a[aria-current="page"]')).to_have_text('Team')


def test_on_phones_the_header_is_one_row_with_a_menu(logged_in):
    page = logged_in('hans')
    page.goto('/week')
    menu = page.locator('.menu-toggle')
    expect(menu).to_be_hidden()  # not on the desktop
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('.app-nav')).to_be_hidden()
    expect(page.locator('.review-shortcut')).to_have_text('Review 2')
    menu.click()
    expect(menu).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('.app-nav a:not([href="/review"])')).to_have_text(
        ['Dashboard', 'Week', 'Month', 'Year', 'Audit'])
    expect(page.locator('.account-toggle')).to_be_hidden()  # its entries are listed directly
    expect(page.locator('.account-links > *')).to_have_text(['Team', 'Settings', 'Log out'])
    expect(page.locator('.account-links button:has-text("Log out")')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('.app-nav')).to_be_hidden()
    expect(menu).to_be_focused()


def test_a_visitor_writes_to_support_and_a_user_finds_name_and_address_from_their_account(browser, base, logged_in):
    page = browser.new_page(base_url=base)
    page.goto('/contact')
    page.click('button:has-text("Send")')
    expect(page.locator('#contact-name-error')).to_be_visible()  # nothing entered yet
    for name, value in (('name', 'Rainer Zufall'), ('email', 'rainer.zufall@example.com'), ('subject', 'Access'),
                        ('text', 'May I join the Platform team?')):
        page.fill(f'#contact-{name}', value)
    page.click('button:has-text("Send")')
    expect(page.locator('#contact [role="status"]')).to_have_text('Thanks, we will answer by e-mail.')
    hans = logged_in('hans')
    hans.goto('/week')
    hans.click('footer a:has-text("Contact")')
    for name, value in (('name', 'Hans Dampf'), ('email', 'hans.dampf@example.com')):
        expect(hans.locator(f'#contact-{name}')).to_have_value(value)
        expect(hans.locator(f'#contact-{name}')).not_to_be_editable()


def test_support_finds_a_new_message_by_the_badge_and_keeps_track_of_it(browser, base, logged_in):
    visitor = browser.new_page(base_url=base)
    visitor.goto('/contact')
    for name, value in (('name', 'Rainer Zufall'), ('email', 'rainer.zufall@example.com'), ('subject', 'Access'),
                        ('text', 'May I join the Platform team?')):
        visitor.fill(f'#contact-{name}', value)
    visitor.click('button:has-text("Send")')
    expect(visitor.locator('#contact [role="status"]')).to_be_visible()
    page = logged_in('klara')
    page.goto('/week')
    expect(page.locator('.account-toggle')).to_have_attribute('aria-label', 'Menu, 1 new contact message')
    page.click('.account-toggle')
    page.click('.account-links a:has-text("Support")')
    page.click('#messages a:has-text("Access")')
    expect(page.locator('a:has-text("Answer by e-mail")')).to_have_attribute(
        'href', 'mailto:rainer.zufall@example.com?subject=Re%3A%20Access')
    page.select_option('#message-status', 'in_progress')
    expect(page.locator('#support-status')).to_have_text('Marked as In progress')
    page.fill('#note-text', 'Asked Hans to invite him')
    page.click('button:has-text("Add note")')
    expect(page.locator('.history-list li')).to_have_text([
        re.compile('Klara Himmel Status: In progress$'), re.compile('Klara Himmel Note: Asked Hans to invite him$')])
    page.goto('/support')
    expect(page.locator('.account-toggle .badge')).to_have_count(0)  # nothing new any more


@pytest.mark.parametrize('width', [1280, 320])
def test_the_header_stays_at_the_top_and_what_scrolls_into_view_stays_below_it(logged_in, width):
    """SPEC 5.5: e.g. an anchor or the focus (WCAG 2.4.11), on wide screens and on phones."""
    page = logged_in('hans')
    page.set_viewport_size({'width': width, 'height': 500})
    page.goto('/settings')
    section = page.locator('#services')
    section.wait_for()
    section.evaluate('(element) => element.scrollIntoView()')
    header = page.locator('.app-header').bounding_box()
    assert (header['y'], page.evaluate('window.scrollY') > 0, section.bounding_box()['y'] >= header['height']) == (
        0, True, True)


def test_the_dark_mode_switch_saves_the_theme(logged_in):
    page = logged_in('hans')
    page.emulate_media(color_scheme='light')
    page.goto('/week')
    switch = page.locator('.app-user button[aria-label="Dark mode"]')
    expect(page.locator('.app-user > *')).to_have_class(HEADER_END)
    expect(switch).to_have_attribute('aria-pressed', 'false')
    switch.click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    page.goto('/settings')
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    expect(page.locator('input[name="theme"][value="dark"]')).to_be_checked()
    switch.click()
    expect(page.locator('html')).to_have_attribute('data-theme', 'light')
    expect(page.locator('input[name="theme"][value="light"]')).to_be_checked()
    page.request.put('/api/theme', data={'theme': 'system'})  # the other tests show the browser's theme


def test_search_all_time_from_the_navigation_then_a_custom_period(logged_in):
    page = logged_in('hans')
    page.goto('/week')
    page.fill('.nav-search input', 'tng-43')
    page.press('.nav-search input', 'Enter')
    expect(page).to_have_url(re.compile(r'/search\?text=tng-43$'))
    expect(page.locator('.nav-search')).to_be_hidden()  # the page has its own form
    expect(page.locator('#search-text')).to_have_value('tng-43')
    expect(page.locator('.week-summary')).to_contain_text('All time')
    expect(page.locator('#search-start')).to_be_hidden()
    page.select_option('#search-period', 'custom')
    page.fill('#search-start', '2026-10-01')
    page.fill('#search-end', '2026-10-31')
    page.click('#search-form button:has-text("Search")')
    expect(page).to_have_url(re.compile(r'/search\?text=tng-43&period=custom&start=2026-10-01&end=2026-10-31$'))
    expect(page.locator('.week-summary')).to_contain_text('Found 6:00 in 1 entry')
    page.click('button[aria-label="Details of TNG-4347"]')
    expect(page.locator('dialog .entry-details h3')).to_have_text('Mon 26.10.2026 · no times')
