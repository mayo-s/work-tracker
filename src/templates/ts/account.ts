// The user's account: fields for name, username, e-mail address and password (login, registration, setup, settings).

import {
  api, ApiError, errorText, type NewUserInput, type ProfileInput, type TwoFactorSetup, type TwoFactorStatus, type UserView,
} from './api.ts';
import { ask } from './dialog.ts';
import { el } from './dom.ts';
import { field, submit } from './forms.ts';
import { t } from './i18n.ts';

export const PASSWORD_MIN_LENGTH = 12;
const PASSWORD_HINT = t('At least {count} characters with letters, digits and a special character, e.g. ! ? # or %.',
  { count: PASSWORD_MIN_LENGTH });
const USERNAME = /^[A-Za-z0-9][A-Za-z0-9._-]{2,29}$/;
export const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export type AccountValues = {
  username: string; email: string; first_name: string; last_name: string; password: string; repeat: string;
};

export function emptyAccount(): AccountValues {
  return { username: '', email: '', first_name: '', last_name: '', password: '', repeat: '' };
}

/** What keeps the account values from being saved, or null; the password is checked only if `withPassword`. */
export function accountError(values: AccountValues, withPassword: boolean): string | null {
  if (!values.first_name.trim()) {
    return t('Enter your first name.');
  }
  if (!USERNAME.test(values.username.trim())) {
    return t('The username needs 3 to 30 letters, digits, dots, dashes or underscores.');
  }
  if (!EMAIL.test(values.email.trim())) {
    return t('Enter a valid e-mail address.');
  }
  return withPassword ? passwordError(values.password, values.repeat) : null;
}

/** Why a new password is not allowed (the rules of the API), or null: at least 12 characters with letters, digits and a
 * special character (anything but letters, digits and spaces), entered twice the same. */
export function passwordError(password: string, repeat: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return t('The password needs at least {count} characters.', { count: PASSWORD_MIN_LENGTH });
  }
  if (!/\p{L}/u.test(password) || !/\p{Nd}/u.test(password) || !/[^\p{L}\p{N}\s]/u.test(password)) {
    return t('The password needs letters, digits and a special character, e.g. ! ? # or %.');
  }
  return password === repeat ? null : t('The two passwords differ.');
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
    field(prefix, 'first_name', t('First name'), input(prefix, 'first_name', values, { autocomplete: 'given-name' })),
    field(prefix, 'last_name', t('Last name (optional)'), input(prefix, 'last_name', values, { autocomplete: 'family-name' })),
    field(prefix, 'username', t('Username'), input(prefix, 'username', values, { autocomplete: 'username' }),
      t('For logging in, as well as the e-mail address.')),
    field(prefix, 'email', t('E-mail address'), input(prefix, 'email', values, { type: 'email', autocomplete: 'email' })),
  ];
  if (withPassword) {
    fields.push(
      field(prefix, 'password', t('Password'),
        input(prefix, 'password', values, { type: 'password', autocomplete: 'new-password' }),
        PASSWORD_HINT),
      field(prefix, 'repeat', t('Repeat the password'), input(prefix, 'repeat', values,
        { type: 'password', autocomplete: 'new-password' })));
  }
  return fields;
}

/** The login page: log in, then on to `next`; while the database has no root, also "Create root admin"; on AWS
 * Lambda also "Reset root login" with a new setup token. */
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
  const intro = t('This database has no root yet. Root runs the app (registration, admins, backups) and tracks no work; create it once.');
  const deleted = new URLSearchParams(doc.location.search).has('deleted')
    ? [el('p', { class: 'review-status', role: 'status' }, t('Your account and all its data are deleted.'))] : [];
  if (!status.has_users) {
    doc.querySelector('#login-title')!.textContent = t('Create root admin');
    root.replaceChildren(rootForm(status.setup_token ?? false, intro));
  } else {
    root.replaceChildren(...deleted, loginForm(error, fail, next, status.registration, status.root_reset ?? false),
      ...(status.has_root ? [] : [el('h2', { class: 'account-heading' }, t('Create root admin')),
        rootForm(status.setup_token ?? false, intro)]),
      ...(status.root_reset ? [rootResetForm()] : []));
  }
  root.querySelector<HTMLElement>('input')?.focus();
}

/** The registration page (/register, only while an admin has switched registration on); then on to the setup. */
export async function renderRegisterPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#register');
  if (!root) {
    return;
  }
  const status = await api.authStatus();
  if (status.user) {
    window.location.assign('/');
    return;
  }
  const error = el('p', { class: 'form-error field-error', role: 'alert', hidden: true });
  const fail = (failure: unknown, fallback: string): void => {
    error.textContent = errorText(failure, fallback);
    error.hidden = false;
  };
  const form = newUserForm('register',
    t('Create your account. Your days and entries are yours alone; next, the setup asks for your start day, work schedule and PTO days.'),
    t('Register'), api.register, error, fail, '/');
  form.append(el('p', { class: 'muted login-hint' }, `${t('Already registered?')} `, el('a', { href: '/login' }, t('Log in'))));
  root.replaceChildren(form);
  root.querySelector<HTMLElement>('input')?.focus();
}

/** Whether the login failed only for the missing code of the authenticator app (two-factor login). */
export function needsCode(failure: unknown): boolean {
  return failure instanceof ApiError && (failure.details as { code?: string } | null)?.code === 'two_factor_required';
}

/** Only paths of this app, so a link cannot send the user elsewhere after logging in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

function loginForm(
  error: HTMLElement, fail: (failure: unknown, fallback: string) => void, next: string, registration: boolean,
  onLambda: boolean,
): HTMLFormElement {
  const name = el('input', { id: 'login-name', name: 'login', autocomplete: 'username', required: true });
  const password = el('input', { id: 'login-password', name: 'password', type: 'password', autocomplete: 'current-password',
    required: true });
  const code = el('input', { id: 'login-code', name: 'code', inputmode: 'numeric', autocomplete: 'one-time-code' });
  const remember = el('input', { id: 'login-remember', type: 'checkbox' });
  const codeField = el('div', {},
    field('login', 'code', t('Code of your authenticator app'), code,
      t('Six digits, a new one every 30 seconds; or a recovery code.')),
    el('label', { class: 'checkbox-field', for: 'login-remember' }, remember,
      t('Remember this browser for 30 days (not for root)')));
  codeField.hidden = true;  // shown once the password is right and the account uses two-factor login
  const form = el('form', { class: 'card login-form' },
    field('login', 'name', t('Username or e-mail address'), name),
    field('login', 'password', t('Password'), password),
    codeField,
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Log in'))),
    registration && el('p', { class: 'muted login-hint' }, `${t('No account yet?')} `,
      el('a', { href: '/register' }, t('Register'))),
    onLambda
      ? el('p', { class: 'muted login-hint' },
        t('Forgot the password? An admin sets a one-time password for you (for an admin: root).'))
      : el('p', { class: 'muted login-hint' },
        `${t('Forgot the password? Ask an admin for a one-time password, or reset it on the computer running the app:')} `,
        el('code', {}, 'pipenv run python -m src.modules.auth set-password USERNAME')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    api.login(name.value.trim(), password.value, codeField.hidden ? null : code.value.trim(), remember.checked)
      .then(() => window.location.assign(next), (failure: unknown) => {
        if (needsCode(failure)) {
          codeField.hidden = false;
          code.focus();
        }
        fail(failure, t('Logging in failed.'));
      });
  });
  return form;
}

/** Creates root (once per database; on AWS Lambda with the setup token), who is logged in and goes to `/admin`. */
export function rootForm(withToken: boolean, intro = ''): HTMLFormElement {
  const values = emptyAccount();
  const token = el('input', { id: 'root-token', name: 'setup_token', type: 'password', autocomplete: 'off' });
  const error = el('p', { class: 'form-error field-error', role: 'alert', hidden: true });
  const form = el('form', { class: 'card login-form root-form', novalidate: true },
    intro ? el('p', {}, intro) : null,
    ...accountFields('root', values, true),
    withToken ? field('root', 'token', t('Setup token'), token,
      t('The token from the AWS Parameter Store (README, "Deploy to AWS"): only with it root is created.')) : null,
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Create root admin'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = accountError(values, true) ?? (withToken && !token.value.trim() ? t('Enter the setup token.') : null);
    if (problem) {
      error.textContent = problem;
      error.hidden = false;
      return;
    }
    api.createRoot({ ...profileInput(values), password: values.password, setup_token: withToken ? token.value.trim() : null })
      .then(() => window.location.assign('/admin'), (failure: unknown) => {
        error.textContent = errorText(failure, t('Root could not be created.'));
        error.hidden = false;
      });
  });
  return form;
}

/** Root forgot its password (AWS Lambda): a new setup token (README, "Deploy to AWS") sets a new one; on to /admin. */
function rootResetForm(): HTMLElement {
  const values = emptyAccount();
  const token = el('input', { id: 'reset-token', name: 'setup_token', type: 'password', autocomplete: 'off' });
  const fresh = input('reset', 'password', values, { type: 'password', autocomplete: 'new-password' });
  const repeat = input('reset', 'repeat', values, { type: 'password', autocomplete: 'new-password' });
  const error = el('p', { class: 'form-error field-error', role: 'alert', hidden: true });
  const form = el('form', { class: 'card login-form', novalidate: true },
    el('p', {},
      t('For root only: create the setup token parameter again with a new token (README, "Deploy to AWS"), then set a new password with it. The token works once.')),
    field('reset', 'token', t('New setup token'), token),
    field('reset', 'password', t('New password'), fresh, PASSWORD_HINT),
    field('reset', 'repeat', t('Repeat the new password'), repeat),
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Reset root login'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = (token.value.trim() ? null : t('Enter the new setup token.')) ?? passwordError(values.password, values.repeat);
    const show = (message: string): void => {
      error.textContent = message;
      error.hidden = false;
    };
    if (problem) {
      show(problem);
      return;
    }
    api.resetRoot(token.value.trim(), values.password).then(() => window.location.assign('/admin'),
      (failure: unknown) => show(errorText(failure, t("Root's login could not be reset."))));
  });
  return el('details', { class: 'root-reset' }, el('summary', {}, t('Reset root login')), form);
}

/** A form creating a user with `create` (a registration), who is logged in; then on to `next`. */
function newUserForm(
  prefix: string, intro: string, submitLabel: string, create: (input: NewUserInput) => Promise<UserView>,
  error: HTMLElement, fail: (failure: unknown, fallback: string) => void, next: string,
): HTMLFormElement {
  const values = emptyAccount();
  const form = el('form', { class: 'card login-form', novalidate: true },
    el('p', {}, intro),
    ...accountFields(prefix, values, true),
    error,
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, submitLabel)));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = accountError(values, true);
    if (problem) {
      fail(null, problem);
      return;
    }
    create({ ...profileInput(values), password: values.password }).then(() => window.location.assign(next),
      (failure: unknown) => fail(failure, t('The account could not be created.')));
  });
  return form;
}

/** The account section of the settings page: profile and password; a note when the login is off. */
export function accountSection(user: UserView | null, enabled: boolean, reload: (message: string) => void): HTMLElement {
  const section = el('section', { class: 'review-section', id: 'account' }, el('h2', {}, t('Account')));
  if (!enabled || !user) {
    section.append(el('p', { class: 'muted' }, enabled ? t('Not logged in.')
      : t('The login is switched off (WORK_TRACKER_AUTH=off), e.g. for local development.')));
    return section;
  }
  section.append(profileForm(user, reload), el('h3', { class: 'account-heading' }, t('Change password')), passwordForm(reload),
    el('h3', { class: 'account-heading' }, t('Two-factor login')), twoFactorPart(user, reload));
  if (user.role !== 'root') {  // root runs the app and is never deleted
    section.append(el('h3', { class: 'account-heading', id: 'delete-account' }, t('Delete account')), deleteAccountForm(user));
  }
  return section;
}

/** Deletes the own account with all its data (SPEC 5.7, GDPR Art. 17), with the password and, with two-factor login on,
 * a code, after a question; then on to the login page. */
function deleteAccountForm(user: UserView): HTMLElement {
  const password = el('input', { id: 'delete-account-password', type: 'password', autocomplete: 'current-password' });
  const code = el('input', { id: 'delete-account-code', autocomplete: 'one-time-code' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('delete-account', 'password', t('Current password'), password),
    user.two_factor ? field('delete-account', 'code', t('Code of your authenticator app'), code,
      t('Six digits, or a recovery code.')) : null,
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'button-danger' }, t('Delete my account'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'delete-account', ['password', 'code'], async () => {
      const go = await ask(t('Delete your account'), [t('Your account and all your data go now. This cannot be undone.')],
        [{ label: t('Delete my account'), value: true, primary: true }]);
      if (go) {
        await api.deleteAccount(password.value, code.value.trim());
        window.location.assign('/login?deleted');
      }
    }, () => form.querySelectorAll('button').forEach((item) => (item.disabled = false)));  // e.g. after Cancel
  });
  return el('div', {},
    el('p', {},
      t('Your account goes with all your data: days, entries, tickets, settings, your team memberships and the log about your account; your contact messages are anonymized. In other people\'s records you become "Deleted user". This cannot be undone: export your data first if you want to keep it.')),
    form);
}

/** On: the recovery codes left, new ones and (if not required) switching off, each with the password, and a new
 * authenticator app. Off: setting it up with an authenticator app (QR code or the secret as text), confirmed by a first
 * code. */
function twoFactorPart(user: UserView, reload: (message: string) => void): HTMLElement {
  const part = el('div', { class: 'two-factor' }, el('p', { class: 'muted' }, t('Loading…')));
  api.twoFactor().then((status) => part.replaceChildren(...(user.two_factor ? twoFactorOn(status, reload, part)
    : [el('p', {},
      t('Off. With it, every login also asks for a code of an authenticator app on your phone (e.g. Google Authenticator, Microsoft Authenticator, 1Password).')),
    setupButton(part, () => reload(t('Two-factor login is on')))])),
  (failure: unknown) => part.replaceChildren(el('p', { class: 'form-error' }, errorText(failure, t('Could not be loaded.')))));
  return part;
}

function twoFactorOn(status: TwoFactorStatus, reload: (message: string) => void, part: HTMLElement): HTMLElement[] {
  const password = el('input', { id: 'two-factor-password', type: 'password', autocomplete: 'current-password' });
  const fresh = el('button', { type: 'button' }, t('New recovery codes'));
  const off = el('button', { type: 'submit' }, t('Switch off'));
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('two-factor', 'password', t('Current password'), password, status.required
      ? t('For new recovery codes (the old ones stop working).')
      : t('For new recovery codes (the old ones stop working) or switching off.')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, fresh, status.required ? null : off));
  fresh.addEventListener('click', () => {
    void submit(form, 'two-factor', ['password'], () => api.newRecoveryCodes(password.value).then(({ recovery_codes: codes }) =>
      part.replaceChildren(recoveryCodes(codes, () => reload(t('New recovery codes'))))), () => undefined);
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'two-factor', ['password'], () => api.twoFactorOff(password.value),
      () => reload(t('Two-factor login is off')));
  });
  return [
    el('p', {}, status.required
      ? t('On: every login also asks for the code of your authenticator app. Recovery codes left: {left} of 10. Root and admins must use it.',
        { left: status.recovery_left ?? 0 })
      : t('On: every login also asks for the code of your authenticator app. Recovery codes left: {left} of 10.',
        { left: status.recovery_left ?? 0 })),
    form,
    newAppButton(part, reload),
  ];
}

/** A new authenticator app (e.g. on a new phone): password and a current code of the old app (or a recovery code), then
 * the new app's QR code, confirmed by a code of it; the old app works until then. */
function newAppButton(part: HTMLElement, reload: (message: string) => void): HTMLButtonElement {
  const start = el('button', { type: 'button' }, t('New authenticator app'));
  start.addEventListener('click', () => {
    part.replaceChildren(newAppForm((setup) => part.replaceChildren(twoFactorSetup(setup,
      (code) => api.confirmNewApp(code), () => reload(t('The new authenticator app is set up')), t('Use the new app')))));
    part.querySelector<HTMLElement>('input')?.focus();
  });
  return start;
}

function newAppForm(started: (setup: TwoFactorSetup) => void): HTMLFormElement {
  const password = el('input', { id: 'new-app-password', type: 'password', autocomplete: 'current-password' });
  const code = el('input', { id: 'new-app-code', autocomplete: 'one-time-code' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    el('p', {},
      t('Move two-factor login to a new authenticator app, e.g. on a new phone. Your current app keeps working until the new one is confirmed; the recovery codes stay.')),
    field('new-app', 'password', t('Current password'), password),
    field('new-app', 'code', t('Code of your current app'), code, t('Six digits; or a recovery code if the old phone is gone.')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Continue'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    let setup: TwoFactorSetup | null = null;
    void submit(form, 'new-app', ['password', 'code'],
      () => api.startNewApp(password.value, code.value.trim()).then((result) => (setup = result)), () => started(setup!));
  });
  return form;
}

/** Starts the setup in `part`: QR code and secret, a first code, then the recovery codes; `done` after those. */
export function setupButton(part: HTMLElement, done: () => void): HTMLButtonElement {
  const start = el('button', { type: 'button', class: 'primary' }, t('Set up two-factor login'));
  start.addEventListener('click', () => {
    api.startTwoFactor().then((setup) => {
      let codes: string[] = [];
      const confirm = (code: string) => api.confirmTwoFactor(code).then((result) => (codes = result.recovery_codes));
      part.replaceChildren(twoFactorSetup(setup, confirm, () => part.replaceChildren(recoveryCodes(codes, done))));
      part.querySelector<HTMLElement>('input')?.focus();
    }, (failure: unknown) => part.append(el('p', { class: 'form-error' }, errorText(failure, t('The setup could not start.')))));
  });
  return start;
}

/** The QR code and secret of `setup`, and the app's current code for `confirm`; `done` once it is accepted. */
function twoFactorSetup(setup: TwoFactorSetup, confirm: (code: string) => Promise<unknown>, done: () => void,
  button = t('Switch on')): HTMLFormElement {
  const code = el('input', { id: 'two-factor-code', inputmode: 'numeric', autocomplete: 'one-time-code' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    el('p', {}, t('1. Scan the QR code with your authenticator app, or enter the secret by hand.')),
    el('img', { class: 'two-factor-qr', src: setup.qr, alt: t('QR code for your authenticator app'), width: 200, height: 200 }),
    el('p', {}, `${t('Secret:')} `, el('code', { class: 'one-time-password' }, setup.secret)),
    el('p', {}, t('2. Enter the code the app shows now.')),
    field('two-factor', 'code', t('Code'), code, t('Six digits; a new one every 30 seconds.')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, button)));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'two-factor', ['code'], () => confirm(code.value.trim()), done);
  });
  return form;
}

/** The recovery codes, shown only once: each replaces a code of the app once, e.g. when the phone is lost. */
export function recoveryCodes(codes: string[], done: () => void): HTMLElement {
  const saved = el('button', { type: 'button', class: 'primary' }, t('I have saved them'));
  saved.addEventListener('click', done);
  return el('div', { class: 'recovery-codes' },
    el('p', {},
      t('Your recovery codes, shown only now. Keep them apart from your phone (e.g. printed, or in a password manager); each one replaces a code of the app once.')),
    el('ul', { class: 'recovery-code-list' }, ...codes.map((code) => el('li', {}, el('code', {}, code)))),
    el('div', { class: 'form-actions' }, saved));
}

function profileForm(user: UserView, reload: (message: string) => void): HTMLFormElement {
  const values: AccountValues = { ...emptyAccount(), ...user, last_name: user.last_name };
  const form = el('form', { class: 'balance-form', novalidate: true },
    ...accountFields('account', values, false),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Save profile'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'account', ['username', 'email', 'first_name', 'last_name'],
      () => accountError(values, false) ? Promise.reject(new ApiError(422, accountError(values, false)!, null))
        : api.saveProfile(profileInput(values)),
      () => reload(t('Saved the profile')));
  });
  return form;
}

/** The form to change the password; `currentLabel` names the password to give, e.g. the one-time password. */
export function passwordForm(done: (message: string) => void, currentLabel = t('Current password')): HTMLFormElement {
  const current = el('input', { id: 'password-current', type: 'password', autocomplete: 'current-password' });
  const values = emptyAccount();
  const fresh = input('password', 'password', values, { type: 'password', autocomplete: 'new-password' });
  const repeat = input('password', 'repeat', values, { type: 'password', autocomplete: 'new-password' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('password', 'current', currentLabel, current),
    field('password', 'password', t('New password'), fresh, `${PASSWORD_HINT} ${t('Logs out everywhere else.')}`),
    field('password', 'repeat', t('Repeat the new password'), repeat),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit' }, t('Change password'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const problem = passwordError(values.password, values.repeat);
    void submit(form, 'password', ['current', 'password', 'repeat'],
      () => problem ? Promise.reject(new ApiError(422, problem, null)) : api.changePassword(current.value, values.password),
      () => done(t('Changed the password; other sessions are logged out')));
  });
  return form;
}
