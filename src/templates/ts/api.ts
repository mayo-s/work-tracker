// Typed client for the Work Tracker API. The types come from the OpenAPI spec (`npm run api-types`).

import type { components } from './api-types.ts';

type Schemas = components['schemas'];

export type DayType = Schemas['DayType'];
export type DayView = Schemas['DayView'];
export type DayInput = Schemas['DayInput'];
export type EntryView = Schemas['EntryView'];
export type EntryInput = Schemas['EntryInput'];
export type ChangeView = Schemas['ChangeView'];
export type TicketView = Schemas['TicketView'];
export type RenameView = Schemas['RenameView'];
export type AssignmentResult = Schemas['AssignmentResult'];
export type Service = Schemas['Service'];
export type ServiceInput = Schemas['ServiceInput'];
export type ActivityType = Schemas['ActivityType'];
export type ActivityTypeInput = Schemas['ActivityTypeInput'];
export type ReviewView = Schemas['ReviewView'];
export type ReviewEntry = Schemas['ReviewEntry'];
export type ReviewReason = Schemas['ReviewReason'];
export type PeriodTotals = Schemas['PeriodTotals'];
export type WeekReport = Schemas['WeekReport'];
export type MonthReport = Schemas['MonthReport'];
export type YearReport = Schemas['YearReport'];
export type SettingsView = Schemas['SettingsView'];
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
  if (response.status === 204) {
    return undefined as T;
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(response.status, data), data);
  }
  return data as T;
}

function periodQuery(period: Period): string {
  return new URLSearchParams(period).toString();
}

function segment(value: string | number): string {
  return encodeURIComponent(String(value));
}

export const api = {
  days: (period: Period) => request<DayView[]>('GET', `/api/days?${periodQuery(period)}`),
  day: (date: string) => request<DayView>('GET', `/api/days/${segment(date)}`),
  saveDay: (date: string, input: DayInput) => request<DayView>('PUT', `/api/days/${segment(date)}`, input),
  deleteDay: (date: string) => request<void>('DELETE', `/api/days/${segment(date)}`),

  entries: (period: Period) => request<EntryView[]>('GET', `/api/entries?${periodQuery(period)}`),
  entry: (id: number) => request<EntryView>('GET', `/api/entries/${segment(id)}`),
  createEntry: (input: EntryInput) => request<EntryView>('POST', '/api/entries', input),
  updateEntry: (id: number, input: EntryInput) => request<EntryView>('PUT', `/api/entries/${segment(id)}`, input),
  deleteEntry: (id: number) => request<void>('DELETE', `/api/entries/${segment(id)}`),
  entryHistory: (id: number) => request<ChangeView[]>('GET', `/api/entries/${segment(id)}/history`),
  splitEntry: (id: number, ticketKeys: string[]) =>
    request<EntryView[]>('POST', `/api/entries/${segment(id)}/split`, { ticket_keys: ticketKeys }),

  tickets: (withoutService = false) =>
    request<TicketView[]>('GET', withoutService ? '/api/tickets?without_service=true' : '/api/tickets'),
  ticket: (key: string) => request<TicketView>('GET', `/api/tickets/${segment(key)}`),
  setTicketService: (key: string, serviceId: number | null) =>
    request<TicketView>('PUT', `/api/tickets/${segment(key)}`, { service_id: serviceId }),
  assignService: (keys: string[], serviceId: number | null) =>
    request<AssignmentResult>('POST', '/api/tickets/assign-service', { keys, service_id: serviceId }),
  renameTicket: (key: string, newKey: string) =>
    request<RenameView>('POST', `/api/tickets/${segment(key)}/rename`, { new_key: newKey }),

  services: () => request<Service[]>('GET', '/api/services'),
  addService: (input: ServiceInput) => request<Service>('POST', '/api/services', input),
  updateService: (id: number, input: ServiceInput) => request<Service>('PUT', `/api/services/${segment(id)}`, input),
  deleteService: (id: number) => request<void>('DELETE', `/api/services/${segment(id)}`),

  activityTypes: () => request<ActivityType[]>('GET', '/api/activity-types'),
  addActivityType: (input: ActivityTypeInput) => request<ActivityType>('POST', '/api/activity-types', input),
  updateActivityType: (id: number, input: ActivityTypeInput) =>
    request<ActivityType>('PUT', `/api/activity-types/${segment(id)}`, input),
  deleteActivityType: (id: number) => request<void>('DELETE', `/api/activity-types/${segment(id)}`),

  review: () => request<ReviewView>('GET', '/api/review'),
  clearFlag: (id: number) => request<void>('DELETE', `/api/review/flags/${segment(id)}`),

  weekReport: (week: string) => request<WeekReport>('GET', `/api/reports/weeks/${segment(week)}`),
  monthReport: (month: string) => request<MonthReport>('GET', `/api/reports/months/${segment(month)}`),
  yearReport: (year: number) => request<YearReport>('GET', `/api/reports/years/${segment(year)}`),

  settings: () => request<SettingsView>('GET', '/api/settings'),
  saveSettings: (input: SettingsView) => request<SettingsView>('PUT', '/api/settings', input),

  schedules: () => request<ScheduleView[]>('GET', '/api/work-schedules'),
  addSchedule: (input: ScheduleInput) => request<ScheduleView>('POST', '/api/work-schedules', input),
  updateSchedule: (id: number, input: ScheduleInput) => request<ScheduleView>('PUT', `/api/work-schedules/${segment(id)}`, input),
  deleteSchedule: (id: number) => request<void>('DELETE', `/api/work-schedules/${segment(id)}`),

  ptoYears: () => request<PtoYear[]>('GET', '/api/pto-years'),
  savePtoYear: (year: number, input: PtoYearInput) => request<PtoYear>('PUT', `/api/pto-years/${segment(year)}`, input),
  deletePtoYear: (year: number) => request<void>('DELETE', `/api/pto-years/${segment(year)}`),
};
