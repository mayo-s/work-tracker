// Settings page (/settings): overtime balance, PTO days per year, services and activity types.

import {
  api, ApiError, type PtoYear, type PtoYearInput, type ScheduleInput, type ScheduleView, type SettingsView, type Theme,
} from './api.ts';
import { formatDate } from './dates.ts';
import { el } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { field, submit } from './forms.ts';
import { STATE_NAMES, WEEKDAY_NAMES } from './labels.ts';
import { activityTypesTable, servicesTable } from './lists.ts';

const BALANCE_FIELDS = ['balance_start', 'opening_balance'] as const;
const SECTIONS = [
  ['balance', 'Overtime balance'], ['schedules', 'Work schedules'], ['pto-years', 'PTO years'], ['services', 'Services'],
  ['activity-types', 'Activity types'], ['appearance', 'Appearance'],
];
const THEMES: [Theme, string][] = [['system', 'System'], ['light', 'Light'], ['dark', 'Dark']];

/** Shows a theme at once: `data-theme` on <html>, none for `system` (then the system setting decides). */
export function applyTheme(root: HTMLElement, theme: Theme): void {
  if (theme === 'system') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
}

type Weekday = (typeof WEEKDAY_NAMES)[number];

/** `Mon,Tue,Wed,Thu,Fri` → `Mon–Fri`; days not in a row of three or more are listed: `Mon, Wed, Fri`. */
export function formatWorkDays(days: string): string {
  const indexes = days.split(',').map((day) => WEEKDAY_NAMES.indexOf(day as Weekday)).filter((index) => index >= 0);
  const runs: number[][] = [];
  for (const index of indexes) {
    const run = runs.at(-1);
    if (run && run.at(-1) === index - 1) {
      run.push(index);
    } else {
      runs.push([index]);
    }
  }
  return runs.flatMap((run) => (run.length >= 3
    ? [`${WEEKDAY_NAMES[run[0]!]}–${WEEKDAY_NAMES[run.at(-1)!]}`]
    : run.map((index) => WEEKDAY_NAMES[index]!))).join(', ');
}

/** Form values of a work schedule as API input: work days from `Mon,Tue`, company half days from `true` / `false`. */
export function scheduleInput(values: Record<string, string>): ScheduleInput {
  return {
    valid_from: values['valid_from'] ?? '',
    weekly_hours: values['weekly_hours'] ?? '',
    work_days: (values['work_days'] ?? '').split(',').filter(Boolean) as Weekday[],
    state: (values['state'] || 'BE') as ScheduleInput['state'],
    company_half_days: values['company_half_days'] === 'true',
  };
}

/** Form values of a PTO year as API input: empty extra days are 0, an empty carry-over is calculated (null). */
export function ptoYearInput(values: Record<string, string>): PtoYearInput {
  return {
    allowance: Number(values['allowance']),
    extra_days: values['extra_days'] ? Number(values['extra_days']) : 0,
    carried_over: values['carried_over'] ? Number(values['carried_over']) : null,
    note: values['note'] ?? '',
  };
}

function balanceSection(settings: SettingsView, page: Page): HTMLElement {
  const start = el('input', {
    id: 'balance-balance_start', name: 'balance_start', type: 'date', value: settings.balance_start,
  });
  const opening = el('input', { id: 'balance-opening_balance', name: 'opening_balance', value: settings.opening_balance,
    autocomplete: 'off' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('balance', 'balance_start', 'Start date', start, 'First day counted; earlier days are ignored.'),
    field('balance', 'opening_balance', 'Opening balance', opening, 'Overtime before the start day, e.g. 12:30 or -1:45.'),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Save')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'balance', BALANCE_FIELDS,
      () => api.saveSettings({ balance_start: start.value, opening_balance: opening.value.trim() }),
      () => page.reload('Saved the overtime balance'));
  });
  return el('section', { class: 'review-section', id: 'balance' },
    el('h2', {}, 'Overtime balance'),
    el('p', { class: 'muted' }, 'Every day from the start date counts: a work day without times counts its full target as '
      + 'missing. Reports and the balance follow a change right away.'),
    form);
}

function schedulesTable(schedules: ScheduleView[]): EditableTable {
  return {
    id: 'schedules',
    title: 'Work schedules',
    hint: 'The hours per week, split evenly over the work days, give the daily target (40 h / 5 days = 8:00; half days '
      + 'get half of it). Public holidays follow the federal state; 24.12. and 31.12. can be company half days (half PTO, '
      + 'half free). Each schedule applies from its start date until the next one starts, so earlier days keep their '
      + 'target and holidays. Other days count like weekends.',
    noun: 'work schedule',
    fields: [
      { name: 'valid_from', label: 'Valid from', required: true, type: 'date', format: formatDate },
      { name: 'weekly_hours', label: 'Hours per week', required: true, numeric: true,
        placeholder: 'e.g. 40:00' },
      { name: 'work_days', label: 'Work days', required: true, type: 'weekdays', defaultValue: 'Mon,Tue,Wed,Thu,Fri',
        format: formatWorkDays },
      { name: 'state', label: 'Holidays', required: true, type: 'select', defaultValue: 'BE',
        options: Object.entries(STATE_NAMES), format: (state) => STATE_NAMES[state] ?? state },
      { name: 'company_half_days', label: '24.12. / 31.12. half days', required: false, type: 'checkbox', defaultValue: 'true',
        format: (value) => (value === 'true' ? 'yes' : 'no') },
    ],
    usageLabel: 'Daily target',
    items: schedules.map((schedule) => ({
      id: schedule.id,
      label: `from ${formatDate(schedule.valid_from)}`,
      values: {
        valid_from: schedule.valid_from, weekly_hours: schedule.weekly_hours, work_days: schedule.work_days.join(','),
        state: schedule.state ?? 'BE', company_half_days: String(schedule.company_half_days ?? true),
      },
      usage: schedule.daily_target,
    })),
    save: (id, values) => (id === null
      ? api.addSchedule(scheduleInput(values)) : api.updateSchedule(id, scheduleInput(values))),
    remove: (id) => api.deleteSchedule(id),
    deleteQuestion: (item) => `Delete the work schedule ${item.label}? Its days then follow the schedule before it.`,
  };
}

function days(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

function ptoYearsTable(years: PtoYear[]): EditableTable {
  const entered = new Set(years.map((year) => year.year));
  return {
    id: 'pto-years',
    title: 'PTO years',
    hint: 'PTO days per year: the allowance, days granted on top, and a fixed carry-over (e.g. as stated by HR). '
      + 'Without a fixed value, the remainder of the year before is carried over. A year without entry has no PTO account.',
    noun: 'PTO year',
    fields: [
      { name: 'year', label: 'Year', required: true, type: 'number', min: 2000, max: 2100, step: 1, fixed: true },
      { name: 'allowance', label: 'Allowance', required: true, type: 'number', min: 0, step: 0.5, numeric: true },
      { name: 'extra_days', label: 'Extra days', required: false, type: 'number', min: 0, step: 0.5, numeric: true },
      { name: 'carried_over', label: 'Carried over', required: false, type: 'number', step: 0.5, numeric: true,
        placeholder: 'calculated' },
      { name: 'note', label: 'Note', required: false, maxLength: 200 },
    ],
    items: years.map((year) => ({
      id: year.year,
      label: String(year.year),
      values: {
        year: String(year.year), allowance: days(year.allowance), extra_days: days(year.extra_days),
        carried_over: days(year.carried_over), note: year.note ?? '',
      },
    })),
    save: (id, values) => {
      const year = id ?? Number(values['year']);
      if (id === null && entered.has(year)) {
        return Promise.reject(new ApiError(409, `${year} is already entered; edit it in the table`, null));
      }
      return api.savePtoYear(year, ptoYearInput(values));
    },
    remove: (id) => api.deletePtoYear(id),
    deleteQuestion: (item) => `Delete the PTO days of ${item.label}? The year then has no PTO account.`,
  };
}

function appearanceSection(theme: Theme, page: Page): HTMLElement {
  const choices = THEMES.map(([value, label]) => {
    const radio = el('input', { type: 'radio', name: 'theme', value, checked: value === theme });
    radio.addEventListener('change', () => {
      applyTheme(document.documentElement, value);
      api.saveTheme(value).then(() => page.reload(`Saved the theme: ${label}`), page.fail);
    });
    return el('label', {}, radio, label);
  });
  return el('section', { class: 'review-section', id: 'appearance' },
    el('h2', {}, 'Appearance'),
    el('p', { class: 'muted' }, 'The color theme of all pages: System follows the light or dark setting of the system.'),
    el('fieldset', { class: 'theme-preview' }, el('legend', {}, 'Theme'), ...choices));
}

function contents(): HTMLElement {
  return el('nav', { class: 'settings-contents', 'aria-label': 'Sections' },
    ...SECTIONS.map(([id, title]) => el('a', { href: `#${id}` }, title)));
}

export async function renderSettingsPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'settings', 'settings-status', async (page) => {
    const [settings, schedules, years, services, activityTypes, tickets, theme] = await Promise.all([
      api.settings(), api.schedules(), api.ptoYears(), api.services(), api.activityTypes(), api.tickets(), api.theme(),
    ]);
    return [
      contents(),
      balanceSection(settings, page),
      tableSection(schedulesTable(schedules), page),
      tableSection(ptoYearsTable(years), page),
      tableSection(servicesTable(services, tickets), page),
      tableSection(activityTypesTable(activityTypes), page),
      appearanceSection(theme.theme, page),
    ];
  });
  doc.getElementById(doc.location.hash.slice(1))?.scrollIntoView();  // a link like /settings#services
}
