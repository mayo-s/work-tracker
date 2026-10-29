// Settings page (/settings): overtime balance, PTO days per year, services and activity types.

import { api, ApiError, type PtoYear, type PtoYearInput, type SettingsView } from './api.ts';
import { el } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { field, submit } from './forms.ts';
import { activityTypesTable, servicesTable } from './lists.ts';

const BALANCE_FIELDS = ['balance_start', 'opening_balance'] as const;
const SECTIONS = [
  ['balance', 'Overtime balance'], ['pto-years', 'PTO years'], ['services', 'Services'], ['activity-types', 'Activity types'],
];

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
  const start = el('input', { id: 'balance-balance_start', name: 'balance_start', type: 'date', value: settings.balance_start });
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
        placeholder: 'Carried over (calculated)' },
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

function contents(): HTMLElement {
  return el('nav', { class: 'settings-contents', 'aria-label': 'Sections' },
    ...SECTIONS.map(([id, title]) => el('a', { href: `#${id}` }, title)));
}

export async function renderSettingsPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'settings', 'settings-status', async (page) => {
    const [settings, years, services, activityTypes, tickets] = await Promise.all([
      api.settings(), api.ptoYears(), api.services(), api.activityTypes(), api.tickets(),
    ]);
    return [
      contents(),
      balanceSection(settings, page),
      tableSection(ptoYearsTable(years), page),
      tableSection(servicesTable(services, tickets), page),
      tableSection(activityTypesTable(activityTypes), page),
    ];
  });
  doc.getElementById(doc.location.hash.slice(1))?.scrollIntoView();  // a link like /settings#services
}
