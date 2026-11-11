// Admin page (/admin), for root and admins (SPEC 5.7). Root: registration, the full backup and its restore,
// appointing admins and looking after them (status, one-time password). Admins: the teams, their auditors, team roles,
// and looking after everyone else. Both see the users with their role, team, team role and whether they can log in.

import { PASSWORD_MIN_LENGTH } from './account.ts';
import {
  ApiError, api, type AdminSettingsView, type AdminTeamView, type AdminUserInput, type AdminUserView, type AuditorView,
  type AuditView, type DownloadedFile, type RestoreSummary,
} from './api.ts';
import { auditTable } from './audit.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { ask } from './dialog.ts';
import { button, el, scrolling } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { t } from './i18n.ts';
import { field, submit } from './forms.ts';

type TeamRole = NonNullable<AdminUserInput['team_role']>;

type Viewer = 'root' | 'admin';

const ROLES: [AdminUserInput['role'], string][] = [['admin', 'Admin'], ['user', 'User']];  // root is never given
const ROLE_LABELS: Record<AdminUserView['role'], string> = { root: 'Root', admin: 'Admin', user: 'User' };
const TEAM_ROLES: [TeamRole, string][] = [['member', 'Member'], ['team_admin', 'Team admin']];

/** What the viewer may change in a user's row: root the role of anyone and the status of admins; admins team roles and
 * the status of everyone else, and the support role of anyone but root. Nobody changes their own row but an admin their
 * support role, and root's stays as it is. */
export function editable(viewer: Viewer, user: AdminUserView, self: boolean):
  Record<'role' | 'teamRole' | 'status' | 'support', boolean> {
  const fixed = self || user.role === 'root';
  return {
    role: !fixed && viewer === 'root',
    teamRole: !fixed && viewer === 'admin' && Boolean(user.team),
    status: !fixed && viewer === (user.role === 'admin' ? 'root' : 'admin'),
    support: user.role !== 'root' && viewer === 'admin',
  };
}

function timestampCell(value: string | null | undefined): HTMLTableCellElement {
  return el('td', {}, value ? formatTimestamp(value) : el('span', { class: 'muted' }, '—'));
}

/** The input that keeps the user's role, team role, status and support role except for `changes` (never for root,
 * which stays). */
export function userInput(user: AdminUserView, changes: Partial<AdminUserInput>): AdminUserInput {
  return { role: user.role as AdminUserInput['role'], team_role: user.team_role ?? null, active: user.active,
    support: user.support ?? false, ...changes };
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

/** What keeps the passphrase of the full backup from being used, or null: at least 12 characters, entered twice. */
export function passphraseError(passphrase: string, repeat: string): string | null {
  if (passphrase.length < PASSWORD_MIN_LENGTH) {
    return `The passphrase needs at least ${PASSWORD_MIN_LENGTH} characters.`;
  }
  return passphrase === repeat ? null : 'The two passphrases differ.';
}

/** Root downloads the whole database, encrypted with a passphrase that is stored nowhere, and restores it. */
function backupSection(settings: AdminSettingsView, users: AdminUserView[], page: Page): HTMLElement {
  return el('section', { class: 'review-section', id: 'backup' },
    el('h2', {}, 'Full backup'),
    settings.restore_unfinished ? el('p', { class: 'form-error', role: 'alert' }, 'A restore stopped halfway: only you '
      + 'can use the app until it is finished. Restore the file again.') : null,
    el('p', { class: 'muted' }, 'One file of the whole database: all users with their passwords and two-factor login, '
      + "the teams, everyone's records, the logs and the settings; not the sessions. It is compressed and encrypted with "
      + 'the passphrase, which is stored nowhere: keep it apart from the file, without it the backup cannot be restored.'),
    downloadForm(page),
    el('h3', { class: 'account-heading' }, 'Restore'),
    el('p', { class: 'muted' }, 'Everyone but you goes first, then the backup comes in: its users log in with their '
      + "passwords from then. You stay as you are, unless you take over the backup's root login."),
    restoreForm(users.length > 1, page));
}

function downloadForm(page: Page): HTMLFormElement {
  const passphrase = el('input', { id: 'backup-passphrase', type: 'password', autocomplete: 'new-password' });
  const repeat = el('input', { id: 'backup-repeat', type: 'password', autocomplete: 'new-password' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('backup', 'passphrase', 'Passphrase', passphrase, `At least ${PASSWORD_MIN_LENGTH} characters.`),
    field('backup', 'repeat', 'Repeat the passphrase', repeat),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Download backup')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'backup', ['passphrase'], async () => {
      const problem = passphraseError(passphrase.value, repeat.value);
      if (problem) {
        throw new ApiError(422, problem, null);
      }
      saveFile(await api.backup(passphrase.value));
    }, () => page.reload('Downloaded the backup'));
  });
  return form;
}

/** The file of a backup and its passphrase; with anyone but root there, typing `purge` confirms that they go. Without
 * `page` (on /2fa, before root set up two-factor login), root always takes over the backup's root login. */
export function restoreForm(othersExist: boolean, page: Page | null): HTMLFormElement {
  const file = el('input', { id: 'restore-file', type: 'file', accept: '.wtbackup' });
  const passphrase = el('input', { id: 'restore-passphrase', type: 'password', autocomplete: 'off' });
  const rootLogin = el('input', { id: 'restore-root-login', type: 'checkbox', checked: !page });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('restore', 'file', 'Backup file', file),
    field('restore', 'passphrase', 'Passphrase', passphrase),
    page ? el('label', { class: 'checkbox-field', for: 'restore-root-login' }, rootLogin,
      "Take over the backup's root login (username, e-mail address, name, password, two-factor login); you log in "
      + 'again with it afterwards') : null,
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'button-danger' }, 'Restore backup')));
  let summary: RestoreSummary | null = null;
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    summary = null;
    void submit(form, 'restore', ['file', 'passphrase'], async () => {
      const chosen = file.files?.[0];
      if (!chosen || !passphrase.value) {
        throw new ApiError(422, 'Choose the backup file and enter its passphrase.', null);
      }
      const confirm = othersExist ? await askPurge() : null;
      if (othersExist && confirm === null) {
        return;
      }
      summary = await api.restore(toBase64(new Uint8Array(await chosen.arrayBuffer())), passphrase.value, confirm,
        rootLogin.checked);
    }, () => {
      if (summary && rootLogin.checked) {
        window.location.assign('/login');  // this session ended with the login of the backup's root
      } else if (summary) {
        page?.reload(restoredText(summary));
      } else {
        form.querySelectorAll('button').forEach((item) => (item.disabled = false));  // the purge was not confirmed
      }
    });
  });
  return form;
}

/** `purge` once root typed it in the dialog; null when cancelled. */
async function askPurge(): Promise<string | null> {
  const typed = el('input', { id: 'purge-confirm', autocomplete: 'off' });
  const go = await ask('Replace everything with the backup', [
    'Everyone but you goes, with all their records, the teams and the logs; then the backup comes in. This cannot be undone.',
    field('purge', 'confirm', 'Type purge to confirm', typed)], [{ label: 'Restore backup', value: true, primary: true }]);
  if (!go) {
    return null;
  }
  if (typed.value.trim() !== 'purge') {
    throw new ApiError(422, 'Type purge to confirm the restore.', null);
  }
  return 'purge';
}

export function restoredText(summary: RestoreSummary): string {
  const count = (number: number, one: string, more: string): string => `${number} ${number === 1 ? one : more}`;
  return `Restored the backup: ${count(summary.users, 'user', 'users')}, ${count(summary.teams, 'team', 'teams')}, `
    + `${count(summary.entries, 'entry', 'entries')}`;
}

/** The bytes as base64, in slices (a large file would overflow the arguments of one call). */
export function toBase64(bytes: Uint8Array): string {
  let text = '';
  for (let start = 0; start < bytes.length; start += 0x8000) {
    text += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(text);
}

/** Hands the file to the browser to save. */
function saveFile({ blob, name }: DownloadedFile): void {
  const url = URL.createObjectURL(blob);
  const link = el('a', { href: url, download: name, hidden: true });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function roleSelect(user: AdminUserView, page: Page): HTMLSelectElement {
  const select = el('select', { 'aria-label': `Role of ${user.username}` },
    ...ROLES.map(([value, label]) => el('option', { value, selected: user.role === value }, label)));
  select.addEventListener('change', () => {
    const role = select.value as AdminUserInput['role'];
    api.updateAdminUser(user.id, userInput(user, { role }))
      .then(() => page.reload(`${user.username} is now ${roleName(role)}`), page.fail);
  });
  return select;
}

/** The role in their team (only members of a team have one), chosen in place if `canEdit`. */
function teamRoleCell(user: AdminUserView, canEdit: boolean, page: Page): HTMLTableCellElement {
  if (!user.team) {
    return el('td', {}, el('span', { class: 'muted' }, '—'));
  }
  if (!canEdit) {
    return el('td', {}, TEAM_ROLES.find(([value]) => value === user.team_role)?.[1] ?? '');
  }
  const select = el('select', { 'aria-label': `Role of ${user.username} in ${user.team}` },
    ...TEAM_ROLES.map(([value, label]) => el('option', { value, selected: user.team_role === value }, label)));
  select.addEventListener('change', () => {
    const teamRole = select.value as TeamRole;
    api.updateAdminUser(user.id, userInput(user, { team_role: teamRole }))
      .then(() => page.reload(`${user.username} is now ${roleName(teamRole)} of ${user.team}`), page.fail);
  });
  return el('td', {}, select);
}

/** Whether the typed confirmation is the username (ignoring surrounding spaces). */
export function confirmsDeletion(user: AdminUserView, typed: string): boolean {
  return typed.trim() === user.username;
}

/** Deletes a deactivated user's account (SPEC 5.7, GDPR Art. 17) once the viewer typed the username in the dialog. */
async function deleteUser(user: AdminUserView, page: Page): Promise<void> {
  const typed = el('input', { id: 'delete-confirm', autocomplete: 'off' });
  const go = await ask(`Delete ${user.username}`, [
    `The account goes with all records of ${user.username}, their team memberships and the log about them; their `
    + 'contact messages are anonymized. In other people\'s records they become "Deleted user". This cannot be undone.',
    field('delete', 'confirm', `Type ${user.username} to confirm`, typed)],
  [{ label: 'Delete account', value: true, primary: true }]);
  if (!go) {
    return;
  }
  if (!confirmsDeletion(user, typed.value)) {
    page.fail(new ApiError(422, `Type ${user.username} to delete the account.`, null));
    return;
  }
  api.deleteAdminUser(user.id).then(() => page.reload(`Deleted ${user.username}`), page.fail);
}

/** Active or deactivated, chosen in place if `canEdit`; a deactivation asks first. A deactivated user can be deleted. */
function statusCell(user: AdminUserView, canEdit: boolean, page: Page): HTMLTableCellElement {
  const badge = [
    user.active && user.must_change_password ? el('span', { class: 'badge admin-badge' }, 'One-time password') : '',
    user.two_factor ? el('span', { class: 'badge admin-badge', title: 'Two-factor login is on' }, '2FA') : '',
  ];
  if (!canEdit) {
    return el('td', {}, user.active ? 'Active' : el('span', { class: 'badge warning' }, 'Deactivated'), ...badge);
  }
  const select = el('select', { 'aria-label': `Status of ${user.username}` },
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
  const remove = user.active ? '' : button('Delete', () => void deleteUser(user, page),
    { class: 'button-small button-danger', 'aria-label': `Delete ${user.username}` });
  return el('td', {}, select, remove, ...badge);
}

/** Whether the user answers the messages of the contact page (SPEC 5.14), switched in place if `canEdit`. */
function supportCell(user: AdminUserView, canEdit: boolean, page: Page): HTMLTableCellElement {
  if (!canEdit) {
    return el('td', {}, user.support ? 'Yes' : el('span', { class: 'muted' }, '—'));
  }
  const box = el('input', { type: 'checkbox', checked: Boolean(user.support), 'aria-label': `Support: ${user.username}` });
  box.addEventListener('change', () => {
    api.updateAdminUser(user.id, userInput(user, { support: box.checked }))
      .then(() => page.reload(`${user.username} ${box.checked ? 'now answers' : 'no longer answers'} the contact messages`),
        page.fail);
  });
  return el('td', {}, box);
}

/** The user with this e-mail address, ignoring case and surrounding spaces. */
export function userByEmail(users: AdminUserView[], email: string): AdminUserView | undefined {
  const wanted = email.trim().toLowerCase();
  return users.find((user) => user.email.toLowerCase() === wanted);
}

/** The user with the e-mail address entered, or an error under the field. */
function enteredUser(users: AdminUserView[], email: HTMLInputElement): AdminUserView {
  const user = userByEmail(users, email.value);
  if (!user) {
    throw new ApiError(404, 'No user has this e-mail address.', [{ loc: ['email'], msg: 'No user has this e-mail address.' }]);
  }
  return user;
}

/** For the user with the e-mail address entered: a one-time password, shown once to pass on, or a reset of their
 * two-factor login (a lost phone): root for an admin, an admin for anyone else. */
function loginHelpSection(users: AdminUserView[], viewer: Viewer, page: Page): HTMLElement {
  const email = el('input', { id: 'otp-email', name: 'email', type: 'email', autocomplete: 'off' });
  const reset = el('button', { type: 'button' }, 'Reset two-factor login');
  const form = el('form', { class: 'balance-form invite-form', novalidate: true },
    field('otp', 'email', 'E-mail address', email, 'The exact address of the user (upper and lower case do not matter).'),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Set one-time password'), reset));
  let done = '';
  const finish = (): void => (done ? page.reload(done) : form.querySelectorAll('button').forEach((item) => (item.disabled = false)));
  reset.addEventListener('click', () => {
    done = '';
    void submit(form, 'otp', ['email'], async () => {
      const user = enteredUser(users, email);
      const go = await ask(`Reset the two-factor login of ${user.username}`, [
        `${user.username} logs in with the password only, e.g. after losing the phone; root and admins set it up again `
        + 'right after.'], [{ label: 'Reset two-factor login', value: true, primary: true }]);
      if (go) {
        await api.resetTwoFactor(user.id);
        done = `Reset the two-factor login of ${user.username}`;
      }
    }, finish);
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    done = '';
    void submit(form, 'otp', ['email'], async () => {
      const user = enteredUser(users, email);
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
    }, finish);
  });
  return el('section', { class: 'review-section', id: 'one-time-password' },
    el('h2', {}, 'Login help'),
    el('p', { class: 'muted' }, `For ${viewer === 'root' ? 'an admin' : 'a user'} who forgot their password or lost their `
      + `authenticator app (${viewer === 'root' ? 'users get help from an admin' : 'admins get help from root'}). A `
      + 'one-time password logs them out; at the next login they choose a new password with it. It is shown only once, '
      + 'to pass on in person or by phone. Your own login is changed in your settings.'),
    form);
}

function userRow(user: AdminUserView, viewer: Viewer, me: string | undefined, page: Page): HTMLTableRowElement {
  const self = user.id === me;
  const can = editable(viewer, user, self);
  return el('tr', {},
    el('td', {}, el('strong', {}, user.username), self ? el('span', { class: 'muted' }, ' (you)') : ''),
    el('td', {}, [user.first_name, user.last_name].filter(Boolean).join(' ')),
    el('td', {}, user.email),
    el('td', {}, user.team ?? el('span', { class: 'muted' }, '—')),
    teamRoleCell(user, can.teamRole, page),
    el('td', {}, can.role ? roleSelect(user, page) : ROLE_LABELS[user.role]),
    statusCell(user, can.status, page),
    supportCell(user, can.support, page),
    timestampCell(user.registered_at),
    timestampCell(user.last_login_at));
}

const USERS_HINT: Record<Viewer, string> = {
  root: 'You appoint and remove admins (Role) and look after them: their status, and a one-time password below. Admins '
    + 'look after everyone else and the teams. A deactivated user is logged out and cannot log in; their data is kept until '
    + 'you delete the account, e.g. when they ask for it. Root tracks no work and sees nobody\'s days or entries.',
  admin: 'You give team roles and look after the users: their status, and a one-time password below; root appoints the '
    + 'admins and looks after them. A deactivated user is logged out and cannot log in; their data is kept until you delete '
    + 'the account, e.g. when they ask for it. The team role '
    + 'belongs to the team: a team admin, admin or user, manages the team they are in (its members, invitations and '
    + 'services) and sees its members\' reports; leaving the team ends it. Support answers the messages of the contact '
    + 'page; you can also make yourself support. Otherwise nobody changes their own row.',
};

function usersSection(users: AdminUserView[], viewer: Viewer, me: string | undefined, page: Page): HTMLElement {
  const header = el('tr', {}, ...['Username', 'Name', 'E-mail address', 'Team', 'Team role', 'Role', 'Status', 'Support',
    'Registered', 'Last login'].map((label) => el('th', {}, label)));
  return el('section', { class: 'review-section', id: 'users' },
    el('h2', {}, 'Users'),
    el('p', { class: 'muted' }, USERS_HINT[viewer]),
    scrolling(el('table', { class: 'review-table list-table admin-users' }, el('thead', {}, header),
      el('tbody', {}, ...users.map((user) => userRow(user, viewer, me, page))))));
}

function teamsTable(teams: AdminTeamView[]): EditableTable {
  return {
    id: 'teams',
    title: t('Teams'),
    hint: t('Members share the services of their team; users never see which teams exist, they are invited. "Open" shows a team\'s members, invitations and services. Only a team without members can be deleted.'),
    texts: {
      added: (name) => t('Added team {name}', { name }), saved: (name) => t('Saved team {name}', { name }),
      deleted: (name) => t('Deleted team {name}', { name }), none: t('No teams yet.'), add: t('Add team'),
    },
    fields: [{ name: 'name', label: t('Name'), maxLength: 50, required: true }],
    usageLabel: t('Members'),
    items: teams.map((team) => ({
      id: team.id, label: team.name, values: { name: team.name }, usage: String(team.members),
      link: { href: `/team?team=${team.id}`, label: t('Open') },
    })),
    save: (id, values) => (id === null ? api.addTeam(values['name'] ?? '') : api.renameTeam(id, values['name'] ?? '')),
    remove: (id) => api.deleteTeam(id),
    deleteQuestion: (item) => t('Delete the team {name}? Its open invitations and services go with it.', { name: item.label }),
  };
}

/** Who audits which team, until when; an admin assigns a user or another admin (not themselves) by e-mail address. */
function auditorsSection(auditors: AuditorView[], users: AdminUserView[], teams: AdminTeamView[], page: Page): HTMLElement {
  const row = (auditor: AuditorView): HTMLTableRowElement => el('tr', {},
    el('td', {}, auditor.team), el('td', {}, auditor.user),
    el('td', {}, auditor.until ? formatDate(auditor.until) : el('span', { class: 'muted' }, 'until removed')),
    el('td', { class: 'row-actions' }, button('Remove', () => {
      api.removeAuditor(auditor.team_id, auditor.user_id)
        .then(() => page.reload(`${auditor.user} no longer audits ${auditor.team}`), page.fail);
    })));
  return el('section', { class: 'review-section', id: 'auditors' },
    el('h2', {}, 'Auditors'),
    el('p', { class: 'muted' }, 'An auditor sees the dashboard, week, month and year of everyone who was ever in the team, '
      + 'for the days they belonged to it, read-only (no day notes, no review); the members see who can look. The access '
      + 'ends after the last day, or when removed. Not for yourself.'),
    auditors.length
      ? scrolling(el('table', { class: 'review-table list-table' },
        el('thead', {}, el('tr', {}, ...['Team', 'Auditor', 'Last day'].map((label) => el('th', {}, label)),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...auditors.map(row))))
      : el('p', {}, 'No auditors yet.'),
    teams.length ? auditorForm(users, teams, page) : el('p', { class: 'muted' }, 'Create a team first.'));
}

function auditorForm(users: AdminUserView[], teams: AdminTeamView[], page: Page): HTMLFormElement {
  const email = el('input', { id: 'auditor-email', name: 'email', type: 'email', autocomplete: 'off' });
  const team = el('select', { id: 'auditor-team', name: 'team' },
    ...teams.map((item) => el('option', { value: item.id }, item.name)));
  const until = el('input', { id: 'auditor-until', name: 'until', type: 'date' });
  const form = el('form', { class: 'balance-form invite-form', novalidate: true },
    field('auditor', 'email', 'E-mail address', email, 'The exact address of the user or admin.'),
    field('auditor', 'team', 'Team', team),
    field('auditor', 'until', 'Last day (optional)', until, 'Empty: until removed.'),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Assign')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    let done = '';
    void submit(form, 'auditor', ['email', 'team', 'until'], async () => {
      const user = userByEmail(users, email.value);
      if (!user) {
        throw new ApiError(404, 'No user has this e-mail address.', [{ loc: ['email'], msg: 'No user has this e-mail address.' }]);
      }
      const assigned = await api.assignAuditor(team.value, user.id, until.value || null);
      done = `${assigned.user} audits ${assigned.team}`;
    }, () => page.reload(done));
  });
  return form;
}

function auditSection(entries: AuditView[]): HTMLElement {
  return el('section', { class: 'review-section', id: 'audit' },
    el('h2', {}, 'Audit log'),
    el('p', { class: 'muted' }, 'Who changed roles, team roles or the status of users, set one-time passwords, switched '
      + 'registration or changed teams, and when; the latest 200. Every user sees the changes to their own account in '
      + 'their settings.'),
    auditTable(entries, 'No changes yet.'));
}

export async function renderAdminPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'admin', 'admin-status', async (page) => {
    const [users, audit, status] = await Promise.all([api.adminUsers(), api.adminAudit(), api.authStatus()]);
    const viewer: Viewer = status.user?.role === 'root' ? 'root' : 'admin';
    const shared = [usersSection(users, viewer, status.user?.id, page), loginHelpSection(users, viewer, page),
      auditSection(audit)];
    if (viewer === 'root') {
      const settings = await api.adminSettings();
      return [registrationSection(settings.registration, page), backupSection(settings, users, page), ...shared];
    }
    const [teams, auditors] = await Promise.all([api.adminTeams(), api.adminAuditors()]);
    return [tableSection(teamsTable(teams), page), auditorsSection(auditors, users, teams, page), ...shared];
  });
}
