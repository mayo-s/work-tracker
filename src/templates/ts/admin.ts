// Admin page (/admin): registration on or off, the teams, the users with their role, team, team role and whether they
// can log in, and one-time passwords by e-mail address.

import { ApiError, api, type AdminTeamView, type AdminUserInput, type AdminUserView } from './api.ts';
import { formatTimestamp } from './dates.ts';
import { ask } from './dialog.ts';
import { el } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { field, submit } from './forms.ts';

type TeamRole = NonNullable<AdminUserInput['team_role']>;

const ROLES: [AdminUserInput['role'], string][] = [['admin', 'Admin'], ['user', 'User']];  // root is never given
const TEAM_ROLES: [TeamRole, string][] = [['member', 'Member'], ['team_admin', 'Team admin']];

function timestampCell(value: string | null | undefined): HTMLTableCellElement {
  return el('td', {}, value ? formatTimestamp(value) : el('span', { class: 'muted' }, '—'));
}

/** The input that keeps the user's role, team role and status except for `changes` (never for root, which stays). */
export function userInput(user: AdminUserView, changes: Partial<AdminUserInput>): AdminUserInput {
  return { role: user.role as AdminUserInput['role'], team_role: user.team_role ?? null, active: user.active, ...changes };
}

/** `an admin`, `a user`, `a team admin`, `a member`. */
export function roleName(role: AdminUserInput['role'] | TeamRole): string {
  return { admin: 'an admin', user: 'a user', team_admin: 'a team admin', member: 'a member' }[role];
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
      .then(() => page.reload(`${user.username} is now ${roleName(role)}`), page.fail);
  });
  return select;
}

/** The role in their team: only for members of a team, and nobody changes their own. */
function teamRoleCell(user: AdminUserView, self: boolean, page: Page): HTMLTableCellElement {
  if (!user.team) {
    return el('td', {}, el('span', { class: 'muted' }, '—'));
  }
  const select = el('select', { 'aria-label': `Role of ${user.username} in ${user.team}`, disabled: self },
    ...TEAM_ROLES.map(([value, label]) => el('option', { value, selected: user.team_role === value }, label)));
  select.addEventListener('change', () => {
    const teamRole = select.value as TeamRole;
    api.updateAdminUser(user.id, userInput(user, { team_role: teamRole }))
      .then(() => page.reload(`${user.username} is now ${roleName(teamRole)} of ${user.team}`), page.fail);
  });
  return el('td', {}, select);
}

/** Active or deactivated, chosen in place (not for oneself); a deactivation asks first. */
function statusCell(user: AdminUserView, self: boolean, page: Page): HTMLTableCellElement {
  const select = el('select', { 'aria-label': `Status of ${user.username}`, disabled: self },
    el('option', { value: 'active', selected: user.active }, 'Active'),
    el('option', { value: 'deactivated', selected: !user.active }, 'Deactivated'));
  select.addEventListener('change', () => {
    const active = select.value === 'active';
    if (!active && !window.confirm(`Deactivate ${user.username}? They are logged out and cannot log in until `
      + 'reactivated; their data is kept.')) {
      select.value = 'active';
      return;
    }
    api.updateAdminUser(user.id, userInput(user, { active }))
      .then(() => page.reload(`${active ? 'Reactivated' : 'Deactivated'} ${user.username}`), page.fail);
  });
  return el('td', {}, select,
    user.active && user.must_change_password ? el('span', { class: 'badge admin-badge' }, 'One-time password') : '');
}

/** The user with this e-mail address, ignoring case and surrounding spaces. */
export function userByEmail(users: AdminUserView[], email: string): AdminUserView | undefined {
  const wanted = email.trim().toLowerCase();
  return users.find((user) => user.email.toLowerCase() === wanted);
}

/** Sets a one-time password for the user with the e-mail address entered and shows it once, to pass on. */
function oneTimePasswordSection(users: AdminUserView[], page: Page): HTMLElement {
  const email = el('input', { id: 'otp-email', name: 'email', type: 'email', autocomplete: 'off' });
  const form = el('form', { class: 'balance-form invite-form', novalidate: true },
    field('otp', 'email', 'E-mail address', email, 'The exact address of the user (upper and lower case do not matter).'),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Set one-time password')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    let done = '';
    void submit(form, 'otp', ['email'], async () => {
      const user = userByEmail(users, email.value);
      if (!user) {
        throw new ApiError(404, 'No user has this e-mail address.', [{ loc: ['email'], msg: 'No user has this e-mail address.' }]);
      }
      const go = await ask(`One-time password for ${user.username}`, [
        `${user.username} is logged out, the current password stops working, and at the next login ${user.username} `
        + 'chooses a new one with the one-time password.'], [{ label: 'Set one-time password', value: true, primary: true }]);
      if (!go) {
        return;
      }
      const { password } = await api.oneTimePassword(user.id);
      await ask(`One-time password for ${user.username}`, [
        el('p', {}, el('code', { class: 'one-time-password' }, password)),
        `Give it to ${user.username} in person or by phone. It is shown only now.`], [{ label: 'Done', value: true, primary: true }]);
      done = `Set a one-time password for ${user.username}`;
    }, () => (done ? page.reload(done) : form.querySelectorAll('button').forEach((item) => (item.disabled = false))));
  });
  return el('section', { class: 'review-section', id: 'one-time-password' },
    el('h2', {}, 'One-time password'),
    el('p', { class: 'muted' }, 'For a user who forgot their password: they are logged out, and at the next login they choose '
      + 'a new password with the one-time password. It is shown only once, to pass on in person or by phone. Your own '
      + 'password is changed in your settings.'),
    form);
}

function userRow(user: AdminUserView, me: string | undefined, page: Page): HTMLTableRowElement {
  const self = user.id === me;
  const root = user.role === 'root';  // stays root and active, never in a team
  return el('tr', {},
    el('td', {}, el('strong', {}, user.username), self ? el('span', { class: 'muted' }, ' (you)') : ''),
    el('td', {}, [user.first_name, user.last_name].filter(Boolean).join(' ')),
    el('td', {}, user.email),
    el('td', {}, user.team ?? el('span', { class: 'muted' }, '—')),
    teamRoleCell(user, self, page),
    el('td', {}, root ? 'Root' : roleSelect(user, self, page)),
    root ? el('td', {}, 'Active') : statusCell(user, self, page),
    timestampCell(user.registered_at),
    timestampCell(user.last_login_at));
}

function usersSection(users: AdminUserView[], me: string | undefined, page: Page): HTMLElement {
  const header = el('tr', {}, ...['Username', 'Name', 'E-mail address', 'Team', 'Team role', 'Role', 'Status', 'Registered',
    'Last login'].map((label) => el('th', {}, label)));
  return el('section', { class: 'review-section', id: 'users' },
    el('h2', {}, 'Users'),
    el('p', { class: 'muted' }, 'Admins manage registration and users; users work on their own data only. A deactivated '
      + 'user is logged out and cannot log in; their data is kept. Nobody can demote or deactivate themselves. The team role '
      + 'belongs to the team: a team admin, admin or user, manages the team they are in (its members, invitations and '
      + 'services) and sees its members\' reports; leaving the team ends it. Nobody changes their own team role.'),
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
      usersSection(users, status.user?.id, page), oneTimePasswordSection(users, page),
    ];
  });
}
