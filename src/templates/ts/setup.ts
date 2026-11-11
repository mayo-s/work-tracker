// Setup page (/setup): on a new database, root is created first; then each user sets up their own data in steps,
// saved at once with "Start counting", or from the file of "Export my data".

import { rootForm } from './account.ts';
import { api, errorText, type ImportSummary, type SetupImportInput, type SetupInput, type WorkMode } from './api.ts';
import { formatDate, isoDate, type IsoDate } from './dates.ts';
import { button, el } from './dom.ts';
import { checkDuration, normalizeOnLeave, type DurationRules } from './duration-input.ts';
import { field } from './forms.ts';
import { decimal, t } from './i18n.ts';
import { STATE_NAMES, WEEKDAY_NAMES, weekdayName } from './labels.ts';
import { hasTickets, workModeChoice, workModeLabel } from './work-modes.ts';

type Weekday = (typeof WEEKDAY_NAMES)[number];
type Service = { short_name: string; name: string };

export type SetupState = {
  workMode: WorkMode;
  coding: boolean;  // with tickets: add the activity type Coding
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
};

export type Step = 'Start' | 'Work schedule' | 'PTO' | 'Services' | 'Summary';

const STEPS: Step[] = ['Start', 'Work schedule', 'PTO', 'Services', 'Summary'];

/** The name of a step as shown. */
function stepName(step: Step): string {
  const names: Record<Step, string> = {
    'Start': t('Start'), 'Work schedule': t('Work schedule'), 'PTO': t('PTO'), 'Services': t('Services'),
    'Summary': t('Summary'),
  };
  return names[step];
}
const EXPORT_VERSION = 1;  // the newest export file version this app reads
const OPENING: DurationRules = { signed: true };
const WEEKLY_HOURS: DurationRules = { limit: 168 * 60 };

/** The months of the first year that count: the start month only if starting by the 15th (01.03. → 10, 20.03. → 9). */
export function countedMonths(start: IsoDate): number {
  const [, month = 1, day = 1] = start.split('-').map(Number);
  return 12 - month + (day <= 15 ? 1 : 0);
}

/** PTO days for the counted months, rounded up to half days: 30 days from 01.03. → 25, from 20.03. → 22.5. */
export function proRata(perYear: number, start: IsoDate): number {
  return Math.ceil((perYear * countedMonths(start) * 2) / 12 - 1e-9) / 2;
}

/** The steps for a way of working: services only with ticket entries. */
export function setupSteps(mode: WorkMode): Step[] {
  return hasTickets(mode) ? STEPS : STEPS.filter((step) => step !== 'Services');
}

export function initialState(today: IsoDate): SetupState {
  return {
    workMode: 'tickets', coding: true, start: today, opening: '0:00', weeklyHours: '40:00', workDays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], state: 'BE',
    companyHalfDays: true, perYear: '30', firstYear: String(proRata(30, today)), firstYearChanged: false, services: [],
  };
}

/** The problem that keeps a step from going on, or null. */
export function stepError(state: SetupState, step: Step): string | null {
  const checks: Partial<Record<Step, () => string | null>> = {
    'Start': () => (!state.start ? t('Enter the first day.')
      : checkDuration(state.opening, OPENING).kind === 'ok' ? null
        : t('Enter the opening balance, e.g. 0:00, 12:30, -1:45 or 1.5.')),
    'Work schedule': () => (checkDuration(state.weeklyHours, WEEKLY_HOURS).kind !== 'ok'
      ? t('Enter the hours per week, e.g. 40:00 or 38.5 (at most 168:00).')
      : state.workDays.length ? null : t('Choose at least one work day.')),
    'PTO': () => ([state.perYear, state.firstYear].every((days) => days !== '' && Number(days) >= 0)
      ? null : t('Enter the PTO days.')),
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
    services: hasTickets(state.workMode) ? state.services.filter((service) => service.short_name.trim())
      .map((service) => ({ short_name: service.short_name.trim(), name: service.name.trim() })) : [],
    work_mode: state.workMode,
    coding: hasTickets(state.workMode) && state.coding,
  };
}

/** The content of a chosen export file, or why it cannot be imported. */
export function parseExportFile(text: string): { data: SetupImportInput['data'] } | { problem: string } {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    data = null;
  }
  if (!data || typeof data !== 'object' || (data as { format?: unknown }).format !== 'work-tracker') {
    return { problem: t('This is no Work Tracker export file: choose the file of "Export my data".') };
  }
  const version = (data as { version?: unknown }).version;
  if (typeof version === 'number' && version > EXPORT_VERSION) {
    return { problem: t('The file has version {version}; this Work Tracker reads up to version {newest}.',
      { version, newest: EXPORT_VERSION }) };
  }
  return { data: data as SetupImportInput['data'] };
}

/** What an import wrote, as label and count. */
export function importSummary(summary: ImportSummary): [string, string][] {
  return [
    [t('Days'), summary.days], [t('Entries'), summary.entries], [t('History lines'), summary.history],
    [t('Tickets'), summary.tickets], [t('Services'), summary.services], [t('Activity types'), summary.activity_types],
    [t('Work schedules'), summary.work_schedules], [t('PTO years'), summary.pto_years],
  ].map(([label, count]) => [String(label), String(count)]);
}

/** The summary of the last step as label and value. */
export function summary(state: SetupState): [string, string][] {
  const year = Number(state.start.slice(0, 4));
  const services = setupInput(state).services ?? [];
  const mode = workModeLabel(state.workMode);
  const region = STATE_NAMES[state.state] ?? state.state;
  const rows: [string, string][] = [
    [t('Way of working'), setupInput(state).coding ? t('{mode}, with Coding', { mode }) : mode],
    [t('First day'), formatDate(state.start)],
    [t('Opening balance'), state.opening.trim()],
    [t('Work schedule'), t('{hours} h per week, {days}',
      { hours: state.weeklyHours.trim(), days: state.workDays.map(weekdayName).join(', ') })],
    [t('Public holidays'), state.companyHalfDays ? t('{state}, 24.12. / 31.12. half days', { state: region }) : region],
    [t('PTO'), t('{first} days in {year}, {days} days from {next}', { first: decimal(Number(state.firstYear)), year,
      days: decimal(Number(state.perYear)), next: year + 1 })],
  ];
  if (hasTickets(state.workMode)) {
    rows.push([t('Services'), services.length ? services.map((service) => service.short_name).join(', ') : t('none yet')]);
  }
  return rows;
}

function input(id: string, value: string, onInput: (value: string) => void, attributes = {}): HTMLInputElement {
  const element = el('input', { id, value, autocomplete: 'off', ...attributes });
  element.addEventListener('input', () => onInput(element.value));
  return element;
}

/** A duration field that shows how it was read when left (`38.5` → `38:30`). */
function duration(element: HTMLInputElement, rules: DurationRules): HTMLInputElement {
  normalizeOnLeave(element, () => rules);
  return element;
}

function fileImport(onImport: (file: File | undefined) => void): HTMLElement {
  const file = el('input', { type: 'file', id: 'setup-import-file', accept: '.json,application/json' });
  return el('div', { class: 'card card-surface setup-note' },
    el('strong', {}, `${t('Moving from another Work Tracker?')} `),
    t('Import the file of "Export my data" (settings page) instead of the next steps: it sets up everything at once.'),
    field('setup', 'import-file', t('Export file'), file),
    button(t('Import'), () => onImport(file.files?.[0]), { class: null }));
}

function startStep(state: SetupState, onImport: (file: File | undefined) => void, onMode: () => void): HTMLElement[] {
  const start = input('setup-start', state.start, (value) => (state.start = value), { type: 'date' });
  const coding = el('input', { type: 'checkbox', id: 'setup-coding', checked: state.coding });
  coding.addEventListener('change', () => (state.coding = coding.checked));
  const codingOption = el('label', { class: 'checkbox-field', hidden: !hasTickets(state.workMode) }, coding,
    t('Add the activity type Coding'));
  const mode = workModeChoice(state.workMode, (chosen) => {
    state.workMode = chosen;
    codingOption.hidden = !hasTickets(chosen);
    onMode();
  });
  return [
    el('p', {}, t('The overtime balance counts from the first day on, e.g. the first day at a new job.')),
    el('div', { class: 'setup-fields' },
      field('setup', 'start', t('First day'), start),
      field('setup', 'opening', t('Opening balance'),
        duration(input('setup-opening', state.opening, (value) => (state.opening = value)), OPENING),
        t('Overtime taken over, e.g. 12:30, -1:45 or 1.5; otherwise 0:00.'))),
    el('p', {},
      t('How do you track your work? It decides which fields, report parts and links the pages show; it can be changed later.')),
    mode,
    codingOption,
    fileImport(onImport),
  ];
}

function scheduleStep(state: SetupState): HTMLElement[] {
  const days = WEEKDAY_NAMES.map((day) => {
    const box = el('input', { type: 'checkbox', value: day, checked: state.workDays.includes(day) });
    box.addEventListener('change', () => {
      state.workDays = WEEKDAY_NAMES.filter((name) => name === day ? box.checked : state.workDays.includes(name));
    });
    return el('label', {}, box, weekdayName(day));
  });
  const region = el('select', { id: 'setup-state' },
    ...Object.entries(STATE_NAMES).map(([code, name]) => el('option', { value: code, selected: code === state.state }, name)));
  region.addEventListener('change', () => (state.state = region.value));
  const halfDays = el('input', { type: 'checkbox', checked: state.companyHalfDays });
  halfDays.addEventListener('change', () => (state.companyHalfDays = halfDays.checked));
  return [
    el('p', {}, t('The hours per week are split evenly over the work days (40 h / 5 days = 8:00 per day).')),
    el('div', { class: 'setup-fields' },
      field('setup', 'hours', t('Hours per week'),
        duration(input('setup-hours', state.weeklyHours, (value) => (state.weeklyHours = value)), WEEKLY_HOURS)),
      el('div', { class: 'field' }, el('span', { class: 'field-label' }, t('Work days')),
        el('fieldset', { class: 'weekday-picker' }, el('legend', { class: 'visually-hidden' }, t('Work days')), ...days)),
      field('setup', 'state', t('Public holidays of'), region),
      el('div', { class: 'field' }, el('label', { class: 'checkbox-field' }, halfDays,
        t('24.12. and 31.12. are company half days (half PTO, half free)')))),
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
    el('p', {}, t('PTO days are entered per year; {year} and {next} are set up now, later years on the settings page.',
      { year, next: year + 1 })),
    el('div', { class: 'setup-fields' },
      field('setup', 'per-year', t('PTO days per year'), perYear),
      field('setup', 'first-year', t('PTO days in {year}', { year }), first,
        t('Proposed: {months} of 12 months counted (the start month counts if starting by the 15th), rounded up to half days: {days}. Change it to what was agreed.',
          { months, days: decimal(proposal()) }))),
  ];
}

function servicesStep(state: SetupState, redraw: () => void): HTMLElement[] {
  const rows = state.services.map((service, index) => el('div', { class: 'list-form' },
    input(`setup-service-${index}`, service.short_name, (value) => (service.short_name = value),
      { placeholder: t('Short name, e.g. MSB'), 'aria-label': t('Service {number}: short name', { number: index + 1 }) }),
    input(`setup-service-name-${index}`, service.name, (value) => (service.name = value),
      { placeholder: t('Full name (optional)'), 'aria-label': t('Service {number}: full name', { number: index + 1 }) }),
    button(t('Remove'), () => {
      state.services.splice(index, 1);
      redraw();
    })));
  return [
    el('p', {},
      t('The services the coding work is for; the month report groups it by service. Optional: they can also be added later on the settings page.')),
    ...rows,
    button(t('+ Add service'), () => {
      state.services.push({ short_name: '', name: '' });
      redraw();
    }, { class: 'button-small setup-add' }),
  ];
}

function summaryStep(state: SetupState): HTMLElement[] {
  return [
    el('p', {}, t('Everything can be changed later on the settings page.')),
    el('table', { class: 'card-table setup-summary' },
      el('tbody', {}, ...summary(state).map(([label, value]) => el('tr', {}, el('th', {}, label), el('td', {}, value))))),
  ];
}

function progress(names: Step[], step: number): HTMLElement {
  return el('ol', { class: 'setup-steps' },
    ...names.map((name, index) => el('li', { class: index === step ? 'is-current' : index < step ? 'is-done' : null,
      'aria-current': index === step ? 'step' : null }, stepName(name))));
}

function stepContent(
  state: SetupState, name: Step, draw: () => void, onImport: (file: File | undefined) => void, onMode: () => void,
): HTMLElement[] {
  const builders: Record<Step, () => HTMLElement[]> = {
    'Start': () => startStep(state, onImport, onMode),
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
  const status = await api.authStatus();
  if (status.enabled && !status.user) {  // a new database: root first, who then lets the users in
    doc.querySelector('.review-header h1')!.textContent = t('Create root admin');
    doc.querySelector('.review-header p')!.textContent =
      t('Root runs the app: registration, admins and backups. It tracks no work; the people who do get accounts of their own afterwards.');
    root.replaceChildren(rootForm(status.setup_token ?? false));
    root.querySelector<HTMLElement>('input')?.focus();
    return;
  }
  const state = initialState(isoDate(new Date()));
  const names = (): Step[] => setupSteps(state.workMode);
  let step = 0;
  const error = el('p', { class: 'field-error', role: 'alert', hidden: true });
  root.addEventListener('input', () => (error.hidden = true));
  const fail = (message: string): void => {
    error.textContent = message;
    error.hidden = false;
  };
  const go = (next: number): void => {
    const problem = next > step ? stepError(state, names()[step]!) : null;
    if (problem) {
      fail(problem);
      return;
    }
    step = next;
    draw();
  };
  const startCounting = (): void => {
    api.setup(setupInput(state)).then(() => window.location.assign('/'),
      (failure: unknown) => fail(errorText(failure, t('The setup could not be saved.'))));
  };
  const imported = (summary: ImportSummary): void => {
    root.replaceChildren(el('section', { class: 'card setup-step', 'aria-labelledby': 'setup-step-title' },
      el('h2', { id: 'setup-step-title' }, t('Imported')),
      el('p', {}, t('Your data is set up from the file. Everything can be changed later on the settings page.')),
      el('table', { class: 'card-table setup-summary' }, el('tbody', {},
        ...importSummary(summary).map(([label, count]) => el('tr', {}, el('th', {}, label), el('td', {}, count))))),
      el('div', { class: 'form-actions' }, button(t('Open the dashboard'), () => window.location.assign('/'), { class: 'primary' }))));
    root.querySelector<HTMLElement>('.setup-step button')?.focus();
  };
  const importFile = (file: File | undefined): void => {
    if (!file) {
      fail(t('Choose the file of "Export my data" first.'));
      return;
    }
    file.text().then((text) => {
      const parsed = parseExportFile(text);
      return 'problem' in parsed ? fail(parsed.problem)
        : api.importSetup({ data: parsed.data }).then(imported);
    }).catch((failure: unknown) => fail(errorText(failure, t('The file could not be imported.'))));
  };
  const draw = (): void => {
    if (!state.firstYearChanged) {
      state.firstYear = String(proRata(Number(state.perYear) || 0, state.start));
    }
    const steps = names();
    const content = stepContent(state, steps[step]!, draw, importFile,
      () => root.querySelector('.setup-steps')?.replaceWith(progress(names(), step)));  // keeps the focus on the choice
    error.hidden = true;
    root.replaceChildren(progress(steps, step),
      el('section', { class: 'card setup-step', 'aria-labelledby': 'setup-step-title' },
        el('h2', { id: 'setup-step-title' }, `${step + 1}. ${stepName(steps[step]!)}`), ...content, error,
        el('div', { class: 'form-actions' },
          step > 0 ? button(t('Back'), () => go(step - 1), { class: null }) : null,
          step < steps.length - 1 ? button(t('Next'), () => go(step + 1), { class: 'primary' })
            : button(t('Start counting'), startCounting, { class: 'primary' }))));
    root.querySelector<HTMLElement>('.setup-step input, .setup-step select')?.focus();
  };
  draw();
}
