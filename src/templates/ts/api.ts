// Typed client for the Work Tracker API. The types come from the OpenAPI spec (`npm run api-types`).

import type { components } from './api-types.ts';

type Schemas = components['schemas'];

export type DayType = Schemas['DayType'];
export type DayView = Schemas['DayView'];
export type DayInput = Schemas['DayInput'];
export type DayRangeInput = Schemas['DayRangeInput'];
export type DayRangeResult = Schemas['DayRangeResult'];
export type EntryView = Schemas['EntryView'];
export type EntryInput = Schemas['EntryInput'];
export type ChangeView = Schemas['ChangeView'];
export type TicketView = Schemas['TicketView'];
export type RenameView = Schemas['RenameView'];
export type AssignmentResult = Schemas['AssignmentResult'];
export type Service = Schemas['Service'];
export type ServiceInput = Schemas['ServiceInput'];
export type ServiceChoice = Schemas['ServiceChoice'];
export type ActivityType = Schemas['ActivityType'];
export type ActivityTypeInput = Schemas['ActivityTypeInput'];
export type ReviewView = Schemas['ReviewView'];
export type ReviewEntry = Schemas['ReviewEntry'];
export type ReviewReason = Schemas['ReviewReason'];
export type PeriodTotals = Schemas['PeriodTotals'];
export type WeekReport = Schemas['WeekReport'];
export type MonthReport = Schemas['MonthReport'];
export type YearReport = Schemas['YearReport'];
export type DashboardView = Schemas['DashboardView'];
export type AuthStatus = Schemas['AuthStatus'];
export type UserView = Schemas['UserView'];
export type ProfileInput = Schemas['ProfileInput'];
export type NewUserInput = Schemas['NewUserInput'];
export type RootInput = Schemas['RootInput'];
export type TwoFactorSetup = Schemas['TwoFactorSetup'];
export type TwoFactorStatus = Schemas['TwoFactorStatus'];
export type RecoveryCodes = Schemas['RecoveryCodes'];
export type AdminUserView = Schemas['AdminUserView'];
export type AuditView = Schemas['AuditView'];
export type OneTimePasswordView = Schemas['OneTimePasswordView'];
export type AdminUserInput = Schemas['AdminUserInput'];
export type AdminSettings = Schemas['AdminSettings'];
export type AdminTeamView = Schemas['AdminTeamView'];
export type TeamPageView = Schemas['TeamPageView'];
export type MemberView = Schemas['MemberView'];
export type AuditorView = Schemas['AuditorView'];
export type AuditorNote = Schemas['AuditorNote'];
export type AuditedTeam = Schemas['AuditedTeam'];
export type InvitationView = Schemas['InvitationView'];
export type InvitationSent = Schemas['InvitationSent'];
export type MyTeamView = Schemas['MyTeamView'];
export type MyInvitationView = Schemas['MyInvitationView'];
export type ReportViewEntry = Schemas['ReportViewEntry'];
export type SettingsView = Schemas['SettingsView'];
export type ThemeView = Schemas['ThemeView'];
export type Theme = ThemeView['theme'];
export type SetupInput = Schemas['SetupInput'];
export type SetupImportInput = Schemas['SetupImportInput'];
export type ImportSummary = Schemas['ImportSummary'];
export type SetupStatus = Schemas['SetupStatus'];
export type PtoYear = Schemas['PtoYear'];
export type PtoYearInput = Schemas['PtoYearInput'];
export type ScheduleView = Schemas['ScheduleView'];
export type ScheduleInput = Schemas['ScheduleInput'];

/** A week like `2026-W44`, or an inclusive date range in ISO format. */
export type Period = { week: string } | { start: string; end: string };

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';

/** An unsuccessful response: HTTP status, a readable message and the response body. */
export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

/** The message of an error body: Falcon's `description`, or the validation messages of spectree. */
export function errorMessage(status: number, body: unknown): string {
  if (Array.isArray(body)) {
    const messages = body.map((item: { msg?: unknown }) => String(item?.msg ?? '')).filter(Boolean);
    if (messages.length) {
      return messages.join('; ');
    }
  }
  if (body && typeof body === 'object') {
    const { description, title } = body as { description?: unknown; title?: unknown };
    if (description || title) {
      return String(description ?? title);
    }
  }
  return `Request failed with status ${status}`;
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (response.status === 401 && !path.startsWith('/api/auth/') && typeof window !== 'undefined') {
    window.location.assign(loginLink(window.location.pathname + window.location.search));  // e.g. the session ended
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(response.status, data), data);
  }
  return data as T;
}

/** The login page that returns to `next` afterwards. */
export function loginLink(next: string): string {
  return `/login?next=${encodeURIComponent(next)}`;
}

/** The query of a period, with the member of the team view if any. */
function periodQuery(period: Period, member: string | null = null): string {
  return new URLSearchParams({ ...period, ...(member ? { member } : {}) }).toString();
}

/** `?member=…` for the team view, or nothing for the user's own data. */
function memberQuery(member: string | null): string {
  return member ? `?member=${encodeURIComponent(member)}` : '';
}

function segment(value: string | number): string {
  return encodeURIComponent(String(value));
}

export const api = {
  days: (period: Period, member: string | null = null) =>
    request<DayView[]>('GET', `/api/days?${periodQuery(period, member)}`),
  day: (date: string) => request<DayView>('GET', `/api/days/${segment(date)}`),
  saveDay: (date: string, input: DayInput) => request<DayView>('PUT', `/api/days/${segment(date)}`, input),
  deleteDay: (date: string) => request<void>('DELETE', `/api/days/${segment(date)}`),
  bookRange: (input: DayRangeInput) => request<DayRangeResult>('POST', '/api/days/range', input),

  entries: (period: Period, member: string | null = null) =>
    request<EntryView[]>('GET', `/api/entries?${periodQuery(period, member)}`),
  entry: (id: string) => request<EntryView>('GET', `/api/entries/${segment(id)}`),
  createEntry: (input: EntryInput) => request<EntryView>('POST', '/api/entries', input),
  updateEntry: (id: string, input: EntryInput) => request<EntryView>('PUT', `/api/entries/${segment(id)}`, input),
  deleteEntry: (id: string) => request<void>('DELETE', `/api/entries/${segment(id)}`),
  entryHistory: (id: string) => request<ChangeView[]>('GET', `/api/entries/${segment(id)}/history`),
  splitEntry: (id: string, ticketKeys: string[]) =>
    request<EntryView[]>('POST', `/api/entries/${segment(id)}/split`, { ticket_keys: ticketKeys }),

  tickets: (withoutService = false) =>
    request<TicketView[]>('GET', withoutService ? '/api/tickets?without_service=true' : '/api/tickets'),
  ticket: (key: string) => request<TicketView>('GET', `/api/tickets/${segment(key)}`),
  setTicketService: (key: string, serviceId: string | null) =>
    request<TicketView>('PUT', `/api/tickets/${segment(key)}`, { service_id: serviceId }),
  assignService: (keys: string[], serviceId: string | null) =>
    request<AssignmentResult>('POST', '/api/tickets/assign-service', { keys, service_id: serviceId }),
  renameTicket: (key: string, newKey: string) =>
    request<RenameView>('POST', `/api/tickets/${segment(key)}/rename`, { new_key: newKey }),

  services: () => request<Service[]>('GET', '/api/services'),
  serviceChoices: () => request<ServiceChoice[]>('GET', '/api/service-choices'),
  addService: (input: ServiceInput) => request<Service>('POST', '/api/services', input),
  updateService: (id: string, input: ServiceInput) => request<Service>('PUT', `/api/services/${segment(id)}`, input),
  deleteService: (id: string) => request<void>('DELETE', `/api/services/${segment(id)}`),

  activityTypes: () => request<ActivityType[]>('GET', '/api/activity-types'),
  addActivityType: (input: ActivityTypeInput) => request<ActivityType>('POST', '/api/activity-types', input),
  updateActivityType: (id: string, input: ActivityTypeInput) =>
    request<ActivityType>('PUT', `/api/activity-types/${segment(id)}`, input),
  deleteActivityType: (id: string) => request<void>('DELETE', `/api/activity-types/${segment(id)}`),

  review: () => request<ReviewView>('GET', '/api/review'),
  clearFlag: (id: string) => request<void>('DELETE', `/api/review/flags/${segment(id)}`),

  weekReport: (week: string, member: string | null = null) =>
    request<WeekReport>('GET', `/api/reports/weeks/${segment(week)}${memberQuery(member)}`),
  monthReport: (month: string, member: string | null = null) =>
    request<MonthReport>('GET', `/api/reports/months/${segment(month)}${memberQuery(member)}`),
  yearReport: (year: number, member: string | null = null) =>
    request<YearReport>('GET', `/api/reports/years/${segment(year)}${memberQuery(member)}`),
  dashboard: (member: string | null = null) => request<DashboardView>('GET', `/api/dashboard${memberQuery(member)}`),

  authStatus: () => request<AuthStatus>('GET', '/api/auth/status'),
  login: (login: string, password: string, code: string | null = null) =>
    request<UserView>('POST', '/api/auth/login', { login, password, code }),
  twoFactor: () => request<TwoFactorStatus>('GET', '/api/auth/me/two-factor'),
  startTwoFactor: () => request<TwoFactorSetup>('POST', '/api/auth/me/two-factor'),
  confirmTwoFactor: (code: string) => request<RecoveryCodes>('PUT', '/api/auth/me/two-factor', { code }),
  twoFactorOff: (password: string) => request<void>('POST', '/api/auth/me/two-factor/off', { password }),
  newRecoveryCodes: (password: string) =>
    request<RecoveryCodes>('POST', '/api/auth/me/two-factor/recovery', { password }),
  resetTwoFactor: (userId: string) => request<void>('POST', `/api/admin/users/${segment(userId)}/two-factor-reset`),
  logout: () => request<void>('POST', '/api/auth/logout'),
  createRoot: (input: RootInput) => request<UserView>('POST', '/api/auth/root', input),
  resetRoot: (setupToken: string, newPassword: string) =>
    request<UserView>('POST', '/api/auth/root/reset', { setup_token: setupToken, new_password: newPassword }),
  register: (input: NewUserInput) => request<UserView>('POST', '/api/auth/register', input),
  saveProfile: (input: ProfileInput) => request<UserView>('PUT', '/api/auth/me', input),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>('PUT', '/api/auth/me/password', { current_password: currentPassword, new_password: newPassword }),

  adminUsers: () => request<AdminUserView[]>('GET', '/api/admin/users'),
  adminAudit: () => request<AuditView[]>('GET', '/api/admin/audit'),
  myAudit: () => request<AuditView[]>('GET', '/api/auth/me/audit'),
  oneTimePassword: (userId: string) =>
    request<OneTimePasswordView>('POST', `/api/admin/users/${segment(userId)}/one-time-password`),
  updateAdminUser: (id: string, input: AdminUserInput) =>
    request<AdminUserView>('PUT', `/api/admin/users/${segment(id)}`, input),
  adminSettings: () => request<AdminSettings>('GET', '/api/admin/settings'),
  saveAdminSettings: (input: AdminSettings) => request<AdminSettings>('PUT', '/api/admin/settings', input),
  adminTeams: () => request<AdminTeamView[]>('GET', '/api/admin/teams'),
  addTeam: (name: string) => request<AdminTeamView>('POST', '/api/admin/teams', { name }),
  adminAuditors: () => request<AuditorView[]>('GET', '/api/admin/auditors'),
  assignAuditor: (teamId: string, userId: string, until: string | null) =>
    request<AuditorView>('PUT', `/api/admin/teams/${segment(teamId)}/auditors/${segment(userId)}`, { until }),
  removeAuditor: (teamId: string, userId: string) =>
    request<void>('DELETE', `/api/admin/teams/${segment(teamId)}/auditors/${segment(userId)}`),
  renameTeam: (id: string, name: string) => request<AdminTeamView>('PUT', `/api/admin/teams/${segment(id)}`, { name }),
  deleteTeam: (id: string) => request<void>('DELETE', `/api/admin/teams/${segment(id)}`),

  team: (id: string) => request<TeamPageView>('GET', `/api/teams/${segment(id)}`),
  invite: (teamId: string, email: string) =>
    request<InvitationSent>('POST', `/api/teams/${segment(teamId)}/invitations`, { email }),
  withdrawInvitation: (teamId: string, id: string) =>
    request<void>('DELETE', `/api/teams/${segment(teamId)}/invitations/${segment(id)}`),
  removeMember: (teamId: string, userId: string) =>
    request<void>('DELETE', `/api/teams/${segment(teamId)}/members/${segment(userId)}`),
  teamServices: (teamId: string) => request<Service[]>('GET', `/api/teams/${segment(teamId)}/services`),
  addTeamService: (teamId: string, input: ServiceInput) =>
    request<Service>('POST', `/api/teams/${segment(teamId)}/services`, input),
  updateTeamService: (teamId: string, id: string, input: ServiceInput) =>
    request<Service>('PUT', `/api/teams/${segment(teamId)}/services/${segment(id)}`, input),
  deleteTeamService: (teamId: string, id: string) =>
    request<void>('DELETE', `/api/teams/${segment(teamId)}/services/${segment(id)}`),

  myTeam: () => request<MyTeamView>('GET', '/api/team'),
  audits: () => request<AuditedTeam[]>('GET', '/api/audits'),
  leaveTeam: () => request<void>('DELETE', '/api/team'),
  acceptInvitation: (id: string) => request<MyTeamView>('POST', `/api/team/invitations/${segment(id)}/accept`),
  declineInvitation: (id: string) => request<void>('DELETE', `/api/team/invitations/${segment(id)}`),

  setupStatus: () => request<SetupStatus>('GET', '/api/setup'),
  setup: (input: SetupInput) => request<SetupStatus>('POST', '/api/setup', input),
  importSetup: (input: SetupImportInput) => request<ImportSummary>('POST', '/api/setup/import', input),

  settings: () => request<SettingsView>('GET', '/api/settings'),
  saveSettings: (input: SettingsView) => request<SettingsView>('PUT', '/api/settings', input),
  theme: () => request<ThemeView>('GET', '/api/theme'),
  saveTheme: (theme: Theme) => request<ThemeView>('PUT', '/api/theme', { theme }),

  schedules: () => request<ScheduleView[]>('GET', '/api/work-schedules'),
  addSchedule: (input: ScheduleInput) => request<ScheduleView>('POST', '/api/work-schedules', input),
  updateSchedule: (id: string, input: ScheduleInput) => request<ScheduleView>('PUT', `/api/work-schedules/${segment(id)}`, input),
  deleteSchedule: (id: string) => request<void>('DELETE', `/api/work-schedules/${segment(id)}`),

  ptoYears: () => request<PtoYear[]>('GET', '/api/pto-years'),
  savePtoYear: (year: number, input: PtoYearInput) => request<PtoYear>('PUT', `/api/pto-years/${segment(year)}`, input),
  deletePtoYear: (year: number) => request<void>('DELETE', `/api/pto-years/${segment(year)}`),
};
