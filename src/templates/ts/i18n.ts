// Translations (SPEC 5.16): the texts are written in English; the page's language (<html lang>, chosen by the server)
// brings its catalog, /static/locales/<language>.json, the same the server uses. A text without a translation shows in
// English. Modules may translate their constants when they load: main.ts loads the catalog before any page code.

export type Params = Record<string, string | number>;

let entries: Record<string, string> = {};
let current = 'en';

/** The page's language, for the formats of dates and numbers (`Intl`). */
export function language(): string {
  return current;
}

/** Loads the catalog of the page's language before the page shows its texts; English needs none. Without the catalog
 * (e.g. offline) the texts stay English. */
export async function loadCatalog(code: string, fetcher: typeof fetch = fetch): Promise<void> {
  current = code;
  if (code === 'en') {
    entries = {};
    return;
  }
  try {
    const response = await fetcher(`/static/locales/${code}.json`);
    entries = response.ok ? await response.json() as Record<string, string> : {};
  } catch {
    entries = {};
  }
}

/** A count of days (or the like) as the page's language writes it, to one decimal: `2.5`, German and Spanish `2,5`. */
export function decimal(value: number): string {
  return new Intl.NumberFormat(current, { maximumFractionDigits: 1, useGrouping: false }).format(value);
}

/** The text in the page's language with its placeholders filled in, e.g. `t('Deleted {username}', { username })`. */
export function t(text: string, params: Params = {}): string {
  let translated = entries[text] ?? text;
  for (const [name, value] of Object.entries(params)) {
    translated = translated.replaceAll(`{${name}}`, String(value));
  }
  return translated;
}

/** `one` for a count of 1, else `other`, translated with `{count}` and the other placeholders filled in; `params` may
 * give `count` as shown, e.g. `decimal(14.5)`. */
export function tn(count: number, one: string, other: string, params: Params = {}): string {
  return t(count === 1 ? one : other, { count, ...params });
}

/** Items as a list in the page's language: `A and B`, German `A und B`. */
export function listOf(items: string[]): string {
  return new Intl.ListFormat(current, { type: 'conjunction' }).format(items);
}
