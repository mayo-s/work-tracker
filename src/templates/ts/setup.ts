// Setup page (/setup): the initial setup of a new database in steps, saved at once with "Start".

import { accountError, accountFields, emptyAccount, profileInput, type AccountValues } from './account.ts';
import { api, ApiError, type SetupInput } from './api.ts';
import { formatDate, isoDate, type IsoDate } from './dates.ts';
import { el } from './dom.ts';
import { STATE_NAMES, WEEKDAY_NAMES } from './labels.ts';

type Weekday = (typeof WEEKDAY_NAMES)[number];
type Service = { short_name: string; name: string };

export type SetupState = {
  start: IsoDate;
  opening: string;
  weeklyHours: string;
  workDays: Weekday[];
  state: string;
  companyHalfDays: boolean;
  perYear: string;
  firstYear: string;
  firstYearChanged: boolean;
  services: Service[];
  account: AccountValues | null;  // the first user; null if the database already has one
};

export type Step = 'Login' | 'Start' | 'Work schedule' | 'PTO' | 'Services' | 'Summary';

export function steps(state: SetupState): Step[] {
  return [...(state.account ? ['Login' as const] : []), 'Start', 'Work schedule', 'PTO', 'Services', 'Summary'];
}
const DURATION = /^[+-]?\d+:[0-5]\d$/;

/** The months of the first year that count: the start month only if starting by the 15th (01.03. → 10, 20.03. → 9). */
export function countedMonths(start: IsoDate): number {
  const [, month = 1, day = 1] = start.split('-').map(Number);
  return 12 - month + (day <= 15 ? 1 : 0);
}

/** PTO days for the counted months, rounded up to half days: 30 days from 01.03. → 25, from 20.03. → 22.5. */
export function proRata(perYear: number, start: IsoDate): number {
  return Math.ceil((perYear * countedMonths(start) * 2) / 12 - 1e-9) / 2;
}

export function initialState(today: IsoDate): SetupState {
  return {
    start: today, opening: '0:00', weeklyHours: '40:00', workDays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], state: 'BE',
    companyHalfDays: true, perYear: '30', firstYear: String(proRata(30, today)), firstYearChanged: false, services: [],
    account: emptyAccount(),
  };
}

/** The problem that keeps a step from going on, or null. */
export function stepError(state: SetupState, step: Step): string | null {
  const checks: Partial<Record<Step, () => string | null>> = {
    'Login': () => (state.account ? accountError(state.account, true) : null),
    'Start': () => (!state.start ? 'Enter the first day.'
      : DURATION.test(state.opening.trim()) ? null : 'Enter the opening balance as h:mm, e.g. 0:00.'),
    'Work schedule': () => (!DURATION.test(state.weeklyHours.trim()) ? 'Enter the hours per week as h:mm, e.g. 40:00.'
      : state.workDays.length ? null : 'Choose at least one work day.'),
    'PTO': () => ([state.perYear, state.firstYear].every((days) => days !== '' && Number(days) >= 0)
      ? null : 'Enter the PTO days.'),
  };
  return checks[step]?.() ?? null;
}

export function setupInput(state: SetupState): SetupInput {
  return {
    balance_start: state.start,
    opening_balance: state.opening.trim(),
    schedule: {
      weekly_hours: state.weeklyHours.trim(), work_days: state.workDays, state: state.state as SetupInput['schedule']['state'],
      company_half_days: state.companyHalfDays,
    },
    pto_per_year: Number(state.perYear),
    pto_first_year: Number(state.firstYear),
    services: state.services.filter((service) => service.short_name.trim())
      .map((service) => ({ short_name: service.short_name.trim(), name: service.name.trim() })),
    user: state.account ? { ...profileInput(state.account), password: state.account.password } : null,
  };
}

/** The summary of step 5 as label and value. */
export function summary(state: SetupState): [string, string][] {
  const year = Number(state.start.slice(0, 4));
  const services = setupInput(state).services ?? [];
  const account = state.account;
  return [
    ...(account ? [['Login', `${account.username.trim()} · ${account.email.trim()}`] as [string, string]] : []),
    ['First day', formatDate(state.start)],
    ['Opening balance', state.opening.trim()],
    ['Work schedule', `${state.weeklyHours.trim()} h per week, ${state.workDays.join(', ')}`],
    ['Public holidays',
      (STATE_NAMES[state.state] ?? state.state) + (state.companyHalfDays ? ', 24.12. / 31.12. half days' : '')],
    ['PTO', `${state.firstYear} days in ${year}, ${state.perYear} days from ${year + 1}`],
    ['Services', services.length ? services.map((service) => service.short_name).join(', ') : 'none yet'],
  ];
}

function field(label: string, control: HTMLElement, hint = ''): HTMLElement {
  return el('div', { class: 'field' }, el('label', { for: control.id }, label), control,
    hint ? el('p', { class: 'field-hint muted' }, hint) : null);
}

function input(id: string, value: string, onInput: (value: string) => void, attributes = {}): HTMLInputElement {
  const element = el('input', { id, value, autocomplete: 'off', ...attributes });
  element.addEventListener('input', () => onInput(element.value));
  return element;
}

function importNote(): HTMLElement {
  return el('div', { class: 'card card-surface setup-note' },
    el('strong', {}, 'Coming from the spreadsheet? '),
    'Import its yearly CSV exports first (README, "Import the spreadsheet"), e.g. ',
    el('code', {}, 'pipenv run python -m src.modules.importer "SHEET.csv"'), ', then finish the setup here.');
}

function loginStep(state: SetupState): HTMLElement[] {
  return [
    el('p', {}, 'Your login for the app: log in with the username or the e-mail address.'),
    el('div', { class: 'setup-fields' }, ...accountFields('setup-user', state.account!, true)),
  ];
}

function startStep(state: SetupState, changed: () => void): HTMLElement[] {
  const start = input('setup-start', state.start, (value) => {
    state.start = value;
    changed();
  }, { type: 'date' });
  return [
    el('p', {}, 'The overtime balance counts from the first day on, e.g. the first day at a new job.'),
    el('div', { class: 'setup-fields' },
      field('First day', start),
      field('Opening balance', input('setup-opening', state.opening, (value) => (state.opening = value)),
        'Overtime taken over, e.g. 12:30 or -1:45; otherwise 0:00.')),
    importNote(),
  ];
}

function scheduleStep(state: SetupState): HTMLElement[] {
  const days = WEEKDAY_NAMES.map((day) => {
    const box = el('input', { type: 'checkbox', value: day, checked: state.workDays.includes(day) });
    box.addEventListener('change', () => {
      state.workDays = WEEKDAY_NAMES.filter((name) => name === day ? box.checked : state.workDays.includes(name));
    });
    return el('label', {}, box, day);
  });
  const region = el('select', { id: 'setup-state' },
    ...Object.entries(STATE_NAMES).map(([code, name]) => el('option', { value: code, selected: code === state.state }, name)));
  region.addEventListener('change', () => (state.state = region.value));
  const halfDays = el('input', { type: 'checkbox', checked: state.companyHalfDays });
  halfDays.addEventListener('change', () => (state.companyHalfDays = halfDays.checked));
  return [
    el('p', {}, 'The hours per week are split evenly over the work days (40 h / 5 days = 8:00 per day).'),
    el('div', { class: 'setup-fields' },
      field('Hours per week', input('setup-hours', state.weeklyHours, (value) => (state.weeklyHours = value))),
      el('div', { class: 'field' }, el('span', { class: 'field-label' }, 'Work days'),
        el('fieldset', { class: 'weekday-picker' }, el('legend', { class: 'visually-hidden' }, 'Work days'), ...days)),
      field('Public holidays of', region),
      el('div', { class: 'field' }, el('label', { class: 'checkbox-field' }, halfDays,
        '24.12. and 31.12. are company half days (half PTO, half free)'))),
  ];
}

function ptoStep(state: SetupState): HTMLElement[] {
  const year = Number(state.start.slice(0, 4));
  const months = countedMonths(state.start);
  const proposal = (): number => proRata(Number(state.perYear) || 0, state.start);
  const first = input('setup-first-year', state.firstYear, (value) => {
    state.firstYear = value;
    state.firstYearChanged = true;
  }, { type: 'number', min: 0, step: 0.5 });
  const perYear = input('setup-per-year', state.perYear, (value) => {
    state.perYear = value;
    if (!state.firstYearChanged) {
      state.firstYear = String(proposal());
      first.value = state.firstYear;
    }
  }, { type: 'number', min: 0, step: 0.5 });
  return [
    el('p', {}, `PTO days are entered per year; ${year} and ${year + 1} are set up now, later years on the settings page.`),
    el('div', { class: 'setup-fields' },
      field('PTO days per year', perYear),
      field(`PTO days in ${year}`, first,
        `Proposed: ${months} of 12 months counted (the start month counts if starting by the 15th), rounded up to half `
        + `days: ${proposal()}. Change it to what was agreed.`)),
  ];
}

function servicesStep(state: SetupState, redraw: () => void): HTMLElement[] {
  const rows = state.services.map((service, index) => el('div', { class: 'list-form' },
    input(`setup-service-${index}`, service.short_name, (value) => (service.short_name = value),
      { placeholder: 'Short name, e.g. MSB', 'aria-label': `Service ${index + 1}: short name` }),
    input(`setup-service-name-${index}`, service.name, (value) => (service.name = value),
      { placeholder: 'Full name (optional)', 'aria-label': `Service ${index + 1}: full name` }),
    button('Remove', () => {
      state.services.splice(index, 1);
      redraw();
    }, 'button-small')));
  return [
    el('p', {}, 'The services the coding work is for; the month report groups it by service. Optional: they can also be '
      + 'added later on the settings page.'),
    ...rows,
    button('+ Add service', () => {
      state.services.push({ short_name: '', name: '' });
      redraw();
    }, 'button-small setup-add'),
  ];
}

function summaryStep(state: SetupState): HTMLElement[] {
  return [
    el('p', {}, 'Everything can be changed later on the settings page.'),
    el('table', { class: 'card-table setup-summary' },
      el('tbody', {}, ...summary(state).map(([label, value]) => el('tr', {}, el('th', {}, label), el('td', {}, value))))),
  ];
}

function button(label: string, onClick: () => void, className = ''): HTMLButtonElement {
  const element = el('button', { type: 'button', class: className || null }, label);
  element.addEventListener('click', onClick);
  return element;
}

function progress(names: Step[], step: number): HTMLElement {
  return el('ol', { class: 'setup-steps' },
    ...names.map((name, index) => el('li', { class: index === step ? 'is-current' : index < step ? 'is-done' : null,
      'aria-current': index === step ? 'step' : null }, name)));
}

function stepContent(state: SetupState, name: Step, draw: () => void): HTMLElement[] {
  const builders: Record<Step, () => HTMLElement[]> = {
    'Login': () => loginStep(state), 'Start': () => startStep(state, () => undefined),
    'Work schedule': () => scheduleStep(state),
    'PTO': () => ptoStep(state), 'Services': () => servicesStep(state, draw), 'Summary': () => summaryStep(state),
  };
  return builders[name]();
}

export async function renderSetupPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#setup');
  if (!root) {
    return;
  }
  const state = initialState(isoDate(new Date()));
  state.account = (await api.authStatus()).has_users ? null : state.account;  // a database with a user keeps it
  const names = steps(state);
  let step = 0;
  const error = el('p', { class: 'field-error', role: 'alert', hidden: true });
  root.addEventListener('input', () => (error.hidden = true));
  const fail = (message: string): void => {
    error.textContent = message;
    error.hidden = false;
  };
  const go = (next: number): void => {
    const problem = next > step ? stepError(state, names[step]!) : null;
    if (problem) {
      fail(problem);
      return;
    }
    step = next;
    draw();
  };
  const startCounting = (): void => {
    api.setup(setupInput(state)).then(() => window.location.assign('/'),
      (failure: unknown) => fail(failure instanceof ApiError ? failure.message : 'The setup could not be saved.'));
  };
  const draw = (): void => {
    if (!state.firstYearChanged) {
      state.firstYear = String(proRata(Number(state.perYear) || 0, state.start));
    }
    const content = stepContent(state, names[step]!, draw);
    error.hidden = true;
    root.replaceChildren(progress(names, step),
      el('section', { class: 'card setup-step', 'aria-labelledby': 'setup-step-title' },
        el('h2', { id: 'setup-step-title' }, `${step + 1}. ${names[step]}`), ...content, error,
        el('div', { class: 'form-actions' },
          step > 0 ? button('Back', () => go(step - 1)) : null,
          step < names.length - 1 ? button('Next', () => go(step + 1), 'primary')
            : button('Start', startCounting, 'primary'))));
    root.querySelector<HTMLElement>('.setup-step input, .setup-step select')?.focus();
  };
  draw();
}
