// Translations (SPEC 5.16): the texts are written in English; the page's language (<html lang>, chosen by the server)
// brings its catalog, /static/locales/<language>.json, the same the server uses. A text without a translation shows in
// English.

export type Params = Record<string, string | number>;

let entries: Record<string, string> = {};

/** Loads the catalog of the page's language before the page shows its texts; English needs none. Without the catalog
 * (e.g. offline) the texts stay English. */
export async function loadCatalog(language: string, fetcher: typeof fetch = fetch): Promise<void> {
  if (language === 'en') {
    entries = {};
    return;
  }
  try {
    const response = await fetcher(`/static/locales/${language}.json`);
    entries = response.ok ? await response.json() as Record<string, string> : {};
  } catch {
    entries = {};
  }
}

/** The text in the page's language with its placeholders filled in, e.g. `t('Deleted {username}', { username })`. */
export function t(text: string, params: Params = {}): string {
  let translated = entries[text] ?? text;
  for (const [name, value] of Object.entries(params)) {
    translated = translated.replaceAll(`{${name}}`, String(value));
  }
  return translated;
}

/** `one` for a count of 1, else `other`, translated with `{count}` and the other placeholders filled in. */
export function tn(count: number, one: string, other: string, params: Params = {}): string {
  return t(count === 1 ? one : other, { ...params, count });
}
