"""The main flows in the browser, one per page that changes data, as a user goes through them."""

import re

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
    expect(page.locator('.app-nav a[href="/admin"]')).to_be_visible()


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


def test_split_a_guessed_ticket_then_rename_one(logged_in):
    page = logged_in('hans')
    page.goto('/review')
    page.click('#guessed button:has-text("Split")')
    expect(page.locator('#guessed .rename-form input')).to_have_value('TNG-4347, KP-1482')
    page.click('#guessed .rename-form button:has-text("Split")')
    expect(page.locator('#review-status')).to_contain_text('TNG-4347')
    page.locator('#tickets tr', has_text='KP-1482').locator('button:has-text("Rename")').click()
    page.fill('#tickets .rename-input', 'kp-1483')
    page.click('#tickets .rename-form button:has-text("Rename")')
    expect(page.locator('#review-status')).to_have_text('KP-1482 renamed to KP-1483 (1 entry)')


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
