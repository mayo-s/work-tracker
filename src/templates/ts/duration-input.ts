// Duration fields: the formats people type (1:30, 1.5, 1,5, 1h30m, 90m) and the limit of a field.

import { ask } from './dialog.ts';
import { fromMinutes } from './durations.ts';
import { t } from './i18n.ts';

/** Minutes, and whether they were typed as a plain number (read as hours; the field may ask about minutes). */
export type Duration = { minutes: number; bare: boolean };
/** `limit`: the most a field allows; `signed`: a minus is allowed. */
export type DurationRules = { limit?: number; signed?: boolean };
/** What a typed duration needs: nothing, a question (minutes instead of hours), or the API's error. */
export type DurationCheck =
  | { kind: 'empty' | 'invalid' }
  | { kind: 'ok'; minutes: number }
  | { kind: 'over'; limit: number }
  | { kind: 'minutes'; hours: string; minutes: number };

const HOURS = String.raw`(\d+(?:[.,]\d+)?)`;
const toNumber = (text: string): number => Number(text.replace(',', '.'));
const FORMATS: [RegExp, (match: RegExpMatchArray) => number | null][] = [
  [/^(\d+):(\d{2})$/, ([, hours, minutes]) => hoursAndMinutes(Number(hours), Number(minutes))],
  [new RegExp(`^${HOURS}$`), ([, hours]) => toNumber(hours!) * 60],
  [new RegExp(`^${HOURS} ?h(?: ?(\\d+) ?(?:m|min)?)?$`), ([, hours, minutes]) => (minutes === undefined
    ? toNumber(hours!) * 60 : /^\d+$/.test(hours!) ? hoursAndMinutes(Number(hours), Number(minutes)) : null)],
  [/^(\d+) ?(?:m|min)$/, ([, minutes]) => Number(minutes)],
];

function hoursAndMinutes(hours: number, minutes: number): number | null {
  return minutes < 60 ? hours * 60 + minutes : null;
}

/** The minutes of a duration in any of the formats the API reads, or null; a minus only with `signed`. */
export function parseDuration(text: string, signed = false): Duration | null {
  const cleaned = text.trim().toLowerCase().replace(/\s+/g, ' ');
  const sign = signed && /^[-+]/.test(cleaned) ? cleaned.charAt(0) : '';
  const unsigned = cleaned.slice(sign.length).trim();
  for (const [pattern, toMinutes] of FORMATS) {
    const match = unsigned.match(pattern);
    const minutes = match ? toMinutes(match) : null;
    if (minutes !== null && Number.isInteger(Math.round(minutes * 1e6) / 1e6)) {
      return { minutes: (sign === '-' ? -1 : 1) * Math.round(minutes), bare: FORMATS[1]![0].test(unsigned) };
    }
  }
  return null;
}

/** What the typed duration needs under the field's rules. */
export function checkDuration(text: string, rules: DurationRules): DurationCheck {
  if (!text.trim()) {
    return { kind: 'empty' };
  }
  const duration = parseDuration(text, rules.signed);
  if (duration === null) {
    return { kind: 'invalid' };
  }
  const { minutes, bare } = duration;
  if (rules.limit !== undefined && minutes > rules.limit) {
    const typed = text.trim();
    return bare && /^\d+$/.test(typed) && Number(typed) <= rules.limit
      ? { kind: 'minutes', hours: typed, minutes: Number(typed) } : { kind: 'over', limit: rules.limit };
  }
  return { kind: 'ok', minutes };
}

/** Shows how a duration was read when the field is left (`1h30m` → `1:30`); a plain number over the limit stays as
 * typed, as the field asks about it when saving. */
export function normalizeOnLeave(input: HTMLInputElement, rules: () => DurationRules): void {
  input.addEventListener('change', () => {  // fires when a changed field is left
    const check = checkDuration(input.value, rules());
    if (check.kind === 'ok') {
      input.value = fromMinutes(check.minutes);
      input.dispatchEvent(new Event('input', { bubbles: true }));  // forms that keep their values in state follow
    }
  });
}

/** Settles the field before saving: asks whether a plain number over the limit means minutes. False if cancelled;
 * other problems are left to the API's answer. */
export async function settleDuration(input: HTMLInputElement, rules: DurationRules): Promise<boolean> {
  const check = checkDuration(input.value, rules);
  if (check.kind === 'minutes') {
    const meant = await ask(t('Did you mean {minutes} minutes ({duration})?',
      { minutes: check.minutes, duration: fromMinutes(check.minutes) }),
    [t('{hours} hours is longer than this field allows (at most {limit}).',
      { hours: check.hours, limit: fromMinutes(rules.limit!) })],
    [{ label: t('Yes, {duration}', { duration: fromMinutes(check.minutes) }), value: true, primary: true }]);
    if (!meant) {
      return false;
    }
    input.value = fromMinutes(check.minutes);
    return true;
  }
  if (check.kind === 'ok') {
    input.value = fromMinutes(check.minutes);
  }
  return true;
}

/** The minutes of a clock time `08:15` (as the day form takes it), or null. */
export function clockMinutes(text: string): number | null {
  const match = text.trim().match(/^(\d{1,2}):(\d{2})$/);
  return match && Number(match[1]) < 24 && Number(match[2]) < 60 ? Number(match[1]) * 60 + Number(match[2]) : null;
}
