// Admin page (/admin): registration on or off, and the users with their role and whether they can log in.

import { api, type AdminUserInput, type AdminUserView } from './api.ts';
import { formatDate } from './dates.ts';
import { el } from './dom.ts';
import { button, renderEditablePage, type Page } from './editable-table.ts';

const ROLES: [AdminUserInput['role'], string][] = [['admin', 'Admin'], ['user', 'User']];

/** `2026-10-29T08:05:12` → `29.10.2026 08:05`. */
export function formatTimestamp(value: string): string {
  return `${formatDate(value.slice(0, 10))} ${value.slice(11, 16)}`;
}

function timestampCell(value: string | null | undefined): HTMLTableCellElement {
  return el('td', {}, value ? formatTimestamp(value) : el('span', { class: 'muted' }, '—'));
}

/** The input that keeps a user's role and sets `active`; roles the page does not offer yet count as user. */
export function userInput(user: AdminUserView, changes: Partial<AdminUserInput>): AdminUserInput {
  return { role: user.role === 'admin' ? 'admin' : 'user', active: user.active, ...changes };
}

function registrationSection(open: boolean, page: Page): HTMLElement {
  const box = el('input', { id: 'admin-registration', type: 'checkbox', checked: open });
  box.addEventListener('change', () => {
    api.saveAdminSettings({ registration: box.checked })
      .then(() => page.reload(box.checked ? 'Registration is on' : 'Registration is off'), page.fail);
  });
  return el('section', { class: 'review-section', id: 'registration' },
    el('h2', {}, 'Registration'),
    el('p', { class: 'muted' }, 'While on, the login page links to /register, where anyone who reaches the app can create '
      + 'an account. New users start with empty data of their own and go through the setup.'),
    el('label', { class: 'checkbox-field', for: 'admin-registration' }, box, 'Allow registration'));
}

function roleSelect(user: AdminUserView, self: boolean, page: Page): HTMLSelectElement {
  const select = el('select', { 'aria-label': `Role of ${user.username}`, disabled: self },
    ...ROLES.map(([value, label]) => el('option', { value, selected: user.role === value }, label)));
  select.addEventListener('change', () => {
    const role = select.value as AdminUserInput['role'];
    api.updateAdminUser(user.id, userInput(user, { role }))
      .then(() => page.reload(`${user.username} is now ${role === 'admin' ? 'an admin' : 'a user'}`), page.fail);
  });
  return select;
}

function activeToggle(user: AdminUserView, page: Page): HTMLButtonElement {
  return button(user.active ? 'Deactivate' : 'Reactivate', () => {
    if (user.active && !window.confirm(`Deactivate ${user.username}? They are logged out and cannot log in until `
      + 'reactivated; their data is kept.')) {
      return;
    }
    api.updateAdminUser(user.id, userInput(user, { active: !user.active }))
      .then(() => page.reload(`${user.active ? 'Deactivated' : 'Reactivated'} ${user.username}`), page.fail);
  });
}

function userRow(user: AdminUserView, me: string | undefined, page: Page): HTMLTableRowElement {
  const self = user.id === me;
  return el('tr', {},
    el('td', {}, el('strong', {}, user.username), self ? el('span', { class: 'muted' }, ' (you)') : ''),
    el('td', {}, [user.first_name, user.last_name].filter(Boolean).join(' ')),
    el('td', {}, user.email),
    el('td', {}, roleSelect(user, self, page)),
    el('td', {}, user.active ? 'Active' : el('span', { class: 'badge warning' }, 'Deactivated')),
    timestampCell(user.registered_at),
    timestampCell(user.last_login_at),
    el('td', { class: 'row-actions' }, self ? '' : activeToggle(user, page)));
}

function usersSection(users: AdminUserView[], me: string | undefined, page: Page): HTMLElement {
  const header = el('tr', {}, ...['Username', 'Name', 'E-mail address', 'Role', 'Status', 'Registered', 'Last login']
    .map((label) => el('th', {}, label)), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')));
  return el('section', { class: 'review-section', id: 'users' },
    el('h2', {}, 'Users'),
    el('p', { class: 'muted' }, 'Admins manage registration and users; users work on their own data only. A deactivated '
      + 'user is logged out and cannot log in; their data is kept. Nobody can demote or deactivate themselves.'),
    el('table', { class: 'review-table list-table' }, el('thead', {}, header),
      el('tbody', {}, ...users.map((user) => userRow(user, me, page)))));
}

export async function renderAdminPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'admin', 'admin-status', async (page) => {
    const [settings, users, status] = await Promise.all([api.adminSettings(), api.adminUsers(), api.authStatus()]);
    return [registrationSection(settings.registration, page), usersSection(users, status.user?.id, page)];
  });
}
