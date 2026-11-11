// Settings page (/settings): way of working, overtime balance, schedules, PTO days per year, services, activity types,
// team, theme, export of the own data and account.

import {
  api, ApiError, type AuditorNote, type AuditView, type MyInvitationView, type MyTeamView, type PtoYear,
  type PtoYearInput, type ReportViewEntry, type ScheduleInput, type ScheduleView, type SettingsView, type Theme,
} from './api.ts';
import { auditTable } from './audit.ts';
import { formatDate, formatMonth, formatTimestamp } from './dates.ts';
import { button, el, scrolling } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { accountSection } from './account.ts';
import { normalizeOnLeave, type DurationRules } from './duration-input.ts';
import { field, submit } from './forms.ts';
import { t } from './i18n.ts';
import { STATE_NAMES, WEEKDAY_NAMES, weekdayName } from './labels.ts';
import { activityTypesTable, servicesTable } from './lists.ts';
import { applyTheme } from './theme.ts';
import { workModeChoice } from './work-modes.ts';

const BALANCE_FIELDS = ['balance_start', 'opening_balance'] as const;
const SIGNED: DurationRules = { signed: true };  // the opening balance may be negative
const SECTIONS = [
  ['work-mode', t('Way of working')], ['balance', t('Overtime balance')], ['schedules', t('Work schedules')],
  ['pto-years', t('PTO years')], ['services', t('Services')], ['activity-types', t('Activity types')], ['team', t('Team')],
  ['appearance', t('Appearance')], ['data', t('Your data')], ['account', t('Account')],
  ['account-log', t('Changes to your account')],
];
const THEMES: [Theme, string][] = [['system', t('System')], ['light', t('Light')], ['dark', t('Dark')]];

type Weekday = (typeof WEEKDAY_NAMES)[number];

/** `Mon,Tue,Wed,Thu,Fri` → `Mon–Fri` (in the page's language); days not in a row of three or more are listed:
 * `Mon, Wed, Fri`. */
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
    ? [`${weekdayName(WEEKDAY_NAMES[run[0]!]!)}–${weekdayName(WEEKDAY_NAMES[run.at(-1)!]!)}`]
    : run.map((index) => weekdayName(WEEKDAY_NAMES[index]!)))).join(', ');
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

function workModeSection(settings: SettingsView, page: Page): HTMLElement {
  const choice = workModeChoice(settings.work_mode, (mode, label) => {
    api.saveSettings({ ...settings, work_mode: mode })
      .then(() => page.reload(t('Saved the way of working: {mode}', { mode: label })), page.fail);
  });
  return el('section', { class: 'review-section', id: 'work-mode' },
    el('h2', {}, t('Way of working')),
    el('p', { class: 'muted' },
      t('How you track your work decides which fields, report parts and links the pages show. Changing it deletes nothing: what you recorded before stays visible.')),
    choice);
}

function balanceSection(settings: SettingsView, page: Page): HTMLElement {
  const start = el('input', {
    id: 'balance-balance_start', name: 'balance_start', type: 'date', value: settings.balance_start,
  });
  const opening = el('input', { id: 'balance-opening_balance', name: 'opening_balance', value: settings.opening_balance,
    autocomplete: 'off' });
  const form = el('form', { class: 'balance-form', novalidate: true },
    field('balance', 'balance_start', t('Start date'), start, t('First day counted; earlier days are ignored.')),
    field('balance', 'opening_balance', t('Opening balance'), opening,
      t('Overtime before the start day, e.g. 12:30, -1:45 or 1.5.')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Save'))));
  normalizeOnLeave(opening, () => SIGNED);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'balance', BALANCE_FIELDS,
      () => api.saveSettings({ ...settings, balance_start: start.value, opening_balance: opening.value.trim() }),
      () => page.reload(t('Saved the overtime balance')));
  });
  return el('section', { class: 'review-section', id: 'balance' },
    el('h2', {}, t('Overtime balance')),
    el('p', { class: 'muted' },
      t('Every day from the start date counts: a work day without times counts its full target as missing. Reports and the balance follow a change right away.')),
    form);
}

function schedulesTable(schedules: ScheduleView[]): EditableTable {
  return {
    id: 'schedules',
    title: t('Work schedules'),
    hint: t('The hours per week, split evenly over the work days, give the daily target (40 h / 5 days = 8:00; half days get half of it). Public holidays follow the federal state; 24.12. and 31.12. can be company half days (half PTO, half free). Each schedule applies from its start date until the next one starts, so earlier days keep their target and holidays. Other days count like weekends.'),
    texts: {
      added: (name) => t('Added the work schedule {name}', { name }),
      saved: (name) => t('Saved the work schedule {name}', { name }),
      deleted: (name) => t('Deleted the work schedule {name}', { name }), none: t('No work schedules yet.'),
      add: t('Add work schedule'),
    },
    fields: [
      { name: 'valid_from', label: t('Valid from'), required: true, type: 'date', format: formatDate },
      { name: 'weekly_hours', label: t('Hours per week'), required: true, numeric: true,
        placeholder: t('e.g. 40:00'), duration: { limit: 168 * 60 } },
      { name: 'work_days', label: t('Work days'), required: true, type: 'weekdays', defaultValue: 'Mon,Tue,Wed,Thu,Fri',
        format: formatWorkDays },
      { name: 'state', label: t('Holidays'), required: true, type: 'select', defaultValue: 'BE',
        options: Object.entries(STATE_NAMES), format: (state) => STATE_NAMES[state] ?? state },
      { name: 'company_half_days', label: t('24.12. / 31.12. half days'), required: false, type: 'checkbox',
        defaultValue: 'true', format: (value) => (value === 'true' ? t('yes') : t('no')) },
    ],
    usageLabel: t('Daily target'),
    items: schedules.map((schedule) => ({
      id: schedule.id,
      label: t('from {date}', { date: formatDate(schedule.valid_from) }),
      values: {
        valid_from: schedule.valid_from, weekly_hours: schedule.weekly_hours, work_days: schedule.work_days.join(','),
        state: schedule.state ?? 'BE', company_half_days: String(schedule.company_half_days ?? true),
      },
      usage: schedule.daily_target,
    })),
    save: (id, values) => (id === null
      ? api.addSchedule(scheduleInput(values)) : api.updateSchedule(id, scheduleInput(values))),
    remove: (id) => api.deleteSchedule(id),
    deleteQuestion: (item) => t('Delete the work schedule {name}? Its days then follow the schedule before it.',
      { name: item.label }),
  };
}

function days(value: number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

function ptoYearsTable(years: PtoYear[]): EditableTable {
  const entered = new Set(years.map((year) => year.year));
  return {
    id: 'pto-years',
    title: t('PTO years'),
    hint: t('PTO days per year: the allowance, days granted on top, and a fixed carry-over (e.g. as stated by HR). Without a fixed value, the remainder of the year before is carried over. A year without entry has no PTO account.'),
    texts: {
      added: (name) => t('Added the PTO days of {year}', { year: name }),
      saved: (name) => t('Saved the PTO days of {year}', { year: name }),
      deleted: (name) => t('Deleted the PTO days of {year}', { year: name }), none: t('No PTO years yet.'),
      add: t('Add PTO year'),
    },
    fields: [
      { name: 'year', label: t('Year'), required: true, type: 'number', min: 2000, max: 2100, step: 1, fixed: true },
      { name: 'allowance', label: t('Allowance'), required: true, type: 'number', min: 0, step: 0.5, numeric: true },
      { name: 'extra_days', label: t('Extra days'), required: false, type: 'number', min: 0, step: 0.5, numeric: true },
      { name: 'carried_over', label: t('Carried over'), required: false, type: 'number', step: 0.5, numeric: true,
        placeholder: t('calculated') },
      { name: 'note', label: t('Note'), required: false, maxLength: 200 },
    ],
    items: years.map((year) => ({
      id: String(year.year),  // the year is the item's id
      label: String(year.year),
      values: {
        year: String(year.year), allowance: days(year.allowance), extra_days: days(year.extra_days),
        carried_over: days(year.carried_over), note: year.note ?? '',
      },
    })),
    save: (id, values) => {
      const year = Number(id ?? values['year']);
      if (id === null && entered.has(year)) {
        return Promise.reject(new ApiError(409, t('{year} is already entered; edit it in the table', { year }), null));
      }
      return api.savePtoYear(year, ptoYearInput(values));
    },
    remove: (id) => api.deletePtoYear(Number(id)),
    deleteQuestion: (item) => t('Delete the PTO days of {year}? The year then has no PTO account.', { year: item.label }),
  };
}

function appearanceSection(theme: Theme, page: Page): HTMLElement {
  const choices = THEMES.map(([value, label]) => {
    const radio = el('input', { type: 'radio', name: 'theme', value, checked: value === theme });
    radio.addEventListener('change', () => {
      applyTheme(document.documentElement, value);
      api.saveTheme(value).then(() => page.reload(t('Saved the theme: {theme}', { theme: label })), page.fail);
    });
    return el('label', {}, radio, label);
  });
  return el('section', { class: 'review-section', id: 'appearance' },
    el('h2', {}, t('Appearance')),
    el('p', { class: 'muted' }, t('The color theme of all pages: System follows the light or dark setting of the system.')),
    el('fieldset', { class: 'theme-preview' }, el('legend', {}, t('Theme')), ...choices));
}

function dataSection(): HTMLElement {
  return el('section', { class: 'review-section', id: 'data' },
    el('h2', {}, t('Your data')),
    el('p', { class: 'muted' },
      t('All your own records in one JSON file, e.g. as a backup: settings, work schedules, PTO years, services, activity types, tickets, days, and entries with their history. Your password and team are not in it.')),
    el('div', { class: 'form-actions' }, el('a', { class: 'button', href: '/api/export', download: true }, t('Export my data'))));
}

/** What accepting an invitation means: joining, and leaving the current team if there is one. */
export function acceptQuestion(invitation: MyInvitationView, current: string | null): string {
  return current
    ? t('Join {team}? You leave {current}; the services of {current} your tickets use become personal services.',
      { team: invitation.team_name, current })
    : t('Join {team}?', { team: invitation.team_name });
}

function invitationItem(invitation: MyInvitationView, current: string | null, page: Page): HTMLElement {
  const team = invitation.team_name;
  return el('li', {},
    el('strong', {}, team),
    el('span', { class: 'muted' }, ` · ${t('invited by {name} on {date}',
      { name: invitation.invited_by, date: formatTimestamp(invitation.invited_at) })} `),
    button(t('Accept'), () => {
      if (window.confirm(acceptQuestion(invitation, current))) {
        api.acceptInvitation(invitation.id).then(() => page.reload(t('You joined {team}', { team })), page.fail);
      }
    }, { class: 'button-small primary' }),
    button(t('Decline'), () => {
      api.declineInvitation(invitation.id).then(() => page.reload(t('Declined the invitation to {team}', { team })), page.fail);
    }));
}

/** `Week 2026-W45`, `Month October 2026`, `Year 2026`, `Dashboard`. */
export function reportLabel(view: ReportViewEntry): string {
  const labels: Record<string, () => string> = {
    dashboard: () => t('Dashboard'), week: () => t('Week {period}', { period: view.period }),
    month: () => t('Month {period}', { period: formatMonth(view.period) }), year: () => t('Year {period}', { period: view.period }),
  };
  return labels[view.report]?.() ?? view.report;
}

/** `Hans Dampf (Platform, until 30.11.2026)`: an auditor who can see the user's days in a team. */
export function auditorText(auditor: AuditorNote): string {
  return auditor.until
    ? t('{name} ({team}, until {date})', { name: auditor.name, team: auditor.team, date: formatDate(auditor.until) })
    : `${auditor.name} (${auditor.team})`;
}

/** Who can see the user's reports (team admins, auditors), and who looked (team view). */
function teamViewInfo(mine: MyTeamView): HTMLElement[] {
  const auditors = mine.auditors ?? [];
  const notes = [
    mine.team && mine.team_admins.length ? el('p', { class: 'muted' },
      t('The team admins of {team} ({names}) can see your dashboard, week, month and year from {date} on, read-only; not your day notes.',
        { team: mine.team.name, names: mine.team_admins.join(', '), date: formatDate(mine.team.joined_on) })) : null,
    auditors.length ? el('p', { class: 'muted' }, t('Auditors can see the same for your days in their team: {auditors}.',
      { auditors: auditors.map(auditorText).join(', ') })) : null,
  ].filter((note): note is HTMLParagraphElement => note !== null);
  if (!notes.length && !mine.viewed_by.length) {
    return [];
  }
  if (notes.length) {
    notes.push(el('p', { class: 'muted' },
      t('They also see your worked and target hours, overtime and hours per activity type in the team report, without descriptions or notes. Looking at that is not in the log below.')));
  }
  const views = mine.viewed_by.map((view) => el('tr', {},
    el('td', {}, formatTimestamp(view.viewed_at)), el('td', {}, view.viewer), el('td', {}, reportLabel(view))));
  return [
    ...notes,
    el('h3', { class: 'account-heading' }, t('Who looked at your reports')),
    views.length
      ? scrolling(el('table', { class: 'review-table list-table' },
        el('thead', {}, el('tr', {}, el('th', {}, t('When')), el('th', {}, t('Who')), el('th', {}, t('Report')))),
        el('tbody', {}, ...views)))
      : el('p', {}, t('Nobody yet.')),
  ];
}

function teamSection(mine: MyTeamView, page: Page): HTMLElement {
  const current = mine.team;
  const invitations = mine.invitations.map((invitation) => invitationItem(invitation, current?.name ?? null, page));
  const leave = current && button(t('Leave the team'), () => {
    if (window.confirm(t('Leave {team}? The team services your tickets use become personal services.', { team: current.name }))) {
      api.leaveTeam().then(() => page.reload(t('You left {team}', { team: current.name })), page.fail);
    }
  });
  return el('section', { class: 'review-section', id: 'team' },
    el('h2', {}, `${t('Team')} `, invitations.length ? el('span', { class: 'badge warning' }, String(invitations.length)) : ''),
    el('p', { class: 'muted' }, current
      ? t('You are in {team} since {date}; you choose its services in your entries.',
        { team: current.name, date: formatDate(current.joined_on) })
      : t('You are not in a team. A team admin invites you by your e-mail address; you then choose the team\'s services in your entries.')),
    leave,
    ...teamViewInfo(mine),
    invitations.length ? el('h3', { class: 'account-heading' }, t('Invitations')) : null,
    invitations.length ? el('ul', { class: 'invitation-list' }, ...invitations) : null);
}

/** What root or an admin changed in the user's account (audit log). */
function accountLogSection(entries: AuditView[]): HTMLElement {
  return el('section', { class: 'review-section', id: 'account-log' },
    el('h2', {}, t('Changes to your account')),
    el('p', { class: 'muted' }, t('Who changed your role, team role or status, or set a one-time password for you, and when.')),
    auditTable(entries, t('No changes yet.')));
}

function contents(): HTMLElement {
  return el('nav', { class: 'settings-contents', 'aria-label': t('Sections') },
    ...SECTIONS.map(([id, title]) => el('a', { href: `#${id}` }, title)));
}

export async function renderSettingsPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'settings', 'settings-status', async (page) => {
    const status = await api.authStatus();
    const account = [accountSection(status.user ?? null, status.enabled, page.reload),
      ...(status.user ? [accountLogSection(await api.myAudit())] : [])];
    if (status.user?.role === 'root') {  // root tracks no work: only how the app looks and its account
      return [appearanceSection((await api.theme()).theme, page), ...account];
    }
    const [settings, schedules, years, services, activityTypes, tickets, theme, mine] = await Promise.all([
      api.settings(), api.schedules(), api.ptoYears(), api.services(), api.activityTypes(), api.tickets(), api.theme(),
      api.myTeam(),
    ]);
    return [
      contents(),
      workModeSection(settings, page),
      balanceSection(settings, page),
      tableSection(schedulesTable(schedules), page),
      tableSection(ptoYearsTable(years), page),
      tableSection(servicesTable(services, tickets), page),
      tableSection(activityTypesTable(activityTypes), page),
      teamSection(mine, page),
      appearanceSection(theme.theme, page),
      dataSection(),
      ...account,
    ];
  });
  doc.getElementById(doc.location.hash.slice(1))?.scrollIntoView();  // a link like /settings#services
}
