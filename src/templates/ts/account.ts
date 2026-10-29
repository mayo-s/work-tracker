// The user's account: fields for name, username, e-mail address and password (login page, setup and settings).

import { api, ApiError, type ProfileInput, type UserView } from './api.ts';
import { el } from './dom.ts';
import { field, submit } from './forms.ts';

export const PASSWORD_MIN_LENGTH = 12;
const USERNAME = /^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export type AccountValues = {
  username: string; email: string; first_name: string; last_name: string; password: string; repeat: string;
};

export function emptyAccount(): AccountValues {
  return { username: '', email: '', first_name: '', last_name: '', password: '', repeat: '' };
}

/** What keeps the account values from being saved, or null; the password is checked only if `withPassword`. */
export function accountError(values: AccountValues, withPassword: boolean): string | null {
  if (!values.first_name.trim()) {
    return 'Enter your first name.';
  }
  if (!USERNAME.test(values.username.trim())) {
    return 'The username needs 3 to 30 letters, digits, dots, dashes or underscores.';
  }
  if (!EMAIL.test(values.email.trim())) {
    return 'Enter a valid e-mail address.';
  }
  return withPassword ? passwordError(values.password, values.repeat) : null;
}

export function passwordError(password: string, repeat: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `The password needs at least ${PASSWORD_MIN_LENGTH} characters.`;
  }
  return password === repeat ? null : 'The two passwords differ.';
}

export function profileInput(values: AccountValues): ProfileInput {
  return {
    username: values.username.trim(), email: values.email.trim(), first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
  };
}

function input(prefix: string, name: keyof AccountValues, values: AccountValues, attributes = {}): HTMLInputElement {
  const element = el('input', { id: `${prefix}-${name}`, name, value: values[name] ?? '', ...attributes });
  element.addEventListener('input', () => (values[name] = element.value));
  return element;
}

/** Labelled fields for name, username and e-mail address, and the password twice if `withPassword`. */
export function accountFields(prefix: string, values: AccountValues, withPassword: boolean): HTMLElement[] {
  const fields = [
    field(prefix, 'first_name', 'First name', input(prefix, 'first_name', values, { autocomplete: 'given-name' })),
    field(prefix, 'last_name', 'Last name (optional)', input(prefix, 'last_name', values, { autocomplete: 'family-name' })),
    field(prefix, 'username', 'Username', input(prefix, 'username', values, { autocomplete: 'username' }),
      'For logging in, as well as the e-mail address.'),
    field(prefix, 'email', 'E-mail address', input(prefix, 'email', values, { type: 'email', autocomplete: 'email' })),
  ];
  if (withPassword) {
    fields.push(
      field(prefix, 'password', 'Password',
        input(prefix, 'password', values, { type: 'password', autocomplete: 'new-password' }),
        `At least ${PASSWORD_MIN_LENGTH} characters.`),
      field(prefix, 'repeat', 'Repeat the password', input(prefix, 'repeat', values,
        { type: 'password', autocomplete: 'new-password' })));
  }
  return fields;
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** The login page: log in, or create the first user of a database that has none; then on to `next`. */
export async function renderLoginPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#login');
  if (!root) {
    return;
  }
  const next = safeNext(new URLSearchParams(doc.location.search).get('next'));
  const status = await api.authStatus();
  if (status.user || !status.enabled) {
    window.location.assign(next);
    return;
  }
  const error = el('p', { class: 'form-error field-error', role: 'alert', hidden: true });
  const fail = (failure: unknown, fallback: string): void => {
    error.textContent = errorText(failure, fallback);
    error.hidden = false;
  };
  if (!status.has_users) {
    doc.querySelector('#login-title')!.textContent = 'Create your login';
    root.replaceChildren(firstUserForm(error, fail, next));
  } else {
    root.replaceChildren(loginForm(error, fail, next));
  }
  root.querySelector<HTMLElement>('input')?.focus();
}

/** Only paths of this app, so a link cannot send the user elsewhere after logging in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

function loginForm(error: HTMLElement, fail: (failure: unknown, fallback: string) => void, next: string): HTMLFormElement {
  const name = el('input', { id: 'login-name', name: 'login', autocomplete: 'username', required: true });
  const password = el('input', { id: 'login-password', name: 'password', type: 'password', autocomplete: 'current-password',
    required: true });
  const form = el('form', { class: 'card login-form' },
    field('login', 'name', 'Username or e-mail address', name),
    field('login', 'password', 'Password', password),
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Log in')),
    el('p', { class: 'muted login-hint' }, 'Forgot the password? Reset it on the computer running the app: ',
      el('code', {}, 'pipenv run python -m src.modules.auth set-password USERNAME')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    api.login(name.value.trim(), password.value).then(() => window.location.assign(next),
      (failure: unknown) => fail(failure, 'Logging in failed.'));
  });
  return form;
}

function firstUserForm(error: HTMLElement, fail: (failure: unknown, fallback: string) => void, next: string): HTMLFormElement {
  const values = emptyAccount();
  const form = el('form', { class: 'card login-form', novalidate: true },
    el('p', {}, 'This database has no login yet. Create it once; from then on, the app asks for it.'),
    ...accountFields('first-user', values, true),
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Create login')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = accountError(values, true);
    if (problem) {
      fail(null, problem);
      return;
    }
    api.firstUser({ ...profileInput(values), password: values.password }).then(() => window.location.assign(next),
      (failure: unknown) => fail(failure, 'The login could not be created.'));
  });
  return form;
}

/** The account section of the settings page: profile and password; a note when the login is off. */
export function accountSection(user: UserView | null, enabled: boolean, reload: (message: string) => void): HTMLElement {
  const section = el('section', { class: 'review-section', id: 'account' }, el('h2', {}, 'Account'));
  if (!enabled || !user) {
    section.append(el('p', { class: 'muted' }, enabled ? 'Not logged in.'
      : 'The login is switched off (WORK_TRACKER_AUTH=off), e.g. for local development.'));
    return section;
  }
  section.append(profileForm(user, reload), el('h3', { class: 'account-heading' }, 'Change password'), passwordForm(reload));
  return section;
}

function profileForm(user: UserView, reload: (message: string) => void): HTMLFormElement {
  const values: AccountValues = { ...emptyAccount(), ...user, last_name: user.last_name };
  const form = el('form', { class: 'balance-form', novalidate: true },
    ...accountFields('account', values, false),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Save profile')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'account', ['username', 'email', 'first_name', 'last_name'],
      () => accountError(values, false) ? Promise.reject(new ApiError(422, accountError(values, false)!, null))
        : api.saveProfile(profileInput(values)),
      () => reload('Saved the profile'));
  });
  return form;
}

function passwordForm(reload: (message: string) => void): HTMLFormElement {
  const current = el('input', { id: 'password-current', type: 'password', autocomplete: 'current-password' });
  const values = emptyAccount();
  const fresh = input('password', 'password', values, { type: 'password', autocomplete: 'new-password' });
  const repeat = input('password', 'repeat', values, { type: 'password', autocomplete: 'new-password' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('password', 'current', 'Current password', current),
    field('password', 'password', 'New password', fresh,
      `At least ${PASSWORD_MIN_LENGTH} characters; logs out everywhere else.`),
    field('password', 'repeat', 'Repeat the new password', repeat),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit' }, 'Change password')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = passwordError(values.password, values.repeat);
    void submit(form, 'password', ['current', 'password', 'repeat'],
      () => problem ? Promise.reject(new ApiError(422, problem, null)) : api.changePassword(current.value, values.password),
      () => reload('Changed the password; other sessions are logged out'));
  });
  return form;
}
