// Admin page (/admin): registration on or off, the teams, and the users with their role, team and whether they can log in.

import { api, type AdminTeamView, type AdminUserInput, type AdminUserView } from './api.ts';
import { formatTimestamp } from './dates.ts';
import { el } from './dom.ts';
import { button, renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';

const ROLES: [AdminUserInput['role'], string][] = [['admin', 'Admin'], ['team_admin', 'Team admin'], ['user', 'User']];

function timestampCell(value: string | null | undefined): HTMLTableCellElement {
  return el('td', {}, value ? formatTimestamp(value) : el('span', { class: 'muted' }, '—'));
}

/** The input that keeps the user's role and status except for `changes`. */
export function userInput(user: AdminUserView, changes: Partial<AdminUserInput>): AdminUserInput {
  return { role: user.role, active: user.active, ...changes };
}

/** `a team admin`, `an admin`, `a user`. */
export function roleName(role: AdminUserInput['role']): string {
  return { admin: 'an admin', team_admin: 'a team admin', user: 'a user' }[role];
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
    ...ROLES.map(([value, label]) => el('option', {
      value, selected: user.role === value, disabled: value === 'team_admin' && !user.team,  // team admins manage their team
    }, label)));
  select.addEventListener('change', () => {
    const role = select.value as AdminUserInput['role'];
    api.updateAdminUser(user.id, userInput(user, { role }))
      .then(() => page.reload(`${user.username} is now ${roleName(role)}`), page.fail);
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
    el('td', {}, user.team ?? el('span', { class: 'muted' }, '—')),
    el('td', {}, roleSelect(user, self, page)),
    el('td', {}, user.active ? 'Active' : el('span', { class: 'badge warning' }, 'Deactivated')),
    timestampCell(user.registered_at),
    timestampCell(user.last_login_at),
    el('td', { class: 'row-actions' }, self ? '' : activeToggle(user, page)));
}

function usersSection(users: AdminUserView[], me: string | undefined, page: Page): HTMLElement {
  const header = el('tr', {}, ...['Username', 'Name', 'E-mail address', 'Team', 'Role', 'Status', 'Registered', 'Last login']
    .map((label) => el('th', {}, label)), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')));
  return el('section', { class: 'review-section', id: 'users' },
    el('h2', {}, 'Users'),
    el('p', { class: 'muted' }, 'Admins manage registration and users; users work on their own data only. A deactivated '
      + 'user is logged out and cannot log in; their data is kept. Nobody can demote or deactivate themselves. A team admin '
      + 'manages the team they are in: its members, invitations and services.'),
    el('table', { class: 'review-table list-table admin-users' }, el('thead', {}, header),
      el('tbody', {}, ...users.map((user) => userRow(user, me, page)))));
}

function teamsTable(teams: AdminTeamView[]): EditableTable {
  return {
    id: 'teams',
    title: 'Teams',
    hint: 'Members share the services of their team; users never see which teams exist, they are invited. "Open" shows a '
      + 'team\'s members, invitations and services. Only a team without members can be deleted.',
    noun: 'team',
    fields: [{ name: 'name', label: 'Name', maxLength: 50, required: true }],
    usageLabel: 'Members',
    items: teams.map((team) => ({
      id: team.id, label: team.name, values: { name: team.name }, usage: String(team.members),
      link: { href: `/team?team=${team.id}`, label: 'Open' },
    })),
    save: (id, values) => (id === null ? api.addTeam(values['name'] ?? '') : api.renameTeam(id, values['name'] ?? '')),
    remove: (id) => api.deleteTeam(id),
    deleteQuestion: (item) => `Delete the team ${item.label}? Its open invitations and services go with it.`,
  };
}

export async function renderAdminPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'admin', 'admin-status', async (page) => {
    const [settings, users, teams, status] = await Promise.all([
      api.adminSettings(), api.adminUsers(), api.adminTeams(), api.authStatus(),
    ]);
    return [
      registrationSection(settings.registration, page), tableSection(teamsTable(teams), page),
      usersSection(users, status.user?.id, page),
    ];
  });
}
