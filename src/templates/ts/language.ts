// The language switch in the header (SPEC 5.16): the code of the page's language, opening a list of the languages,
// each named in its own language. A choice is saved (in the browser, and in the account when logged in) and the page
// shows again in it, as the server renders it.

import { api, type Language } from './api.ts';
import { el } from './dom.ts';
import { t } from './i18n.ts';

export const LANGUAGES: [Language, string][] = [['de', 'Deutsch'], ['en', 'English'], ['es', 'Español']];

/** The name of a language in that language, e.g. `Deutsch`; the code itself for one we do not have. */
export function languageName(code: string): string {
  return LANGUAGES.find(([language]) => language === code)?.[1] ?? code;
}

/** The switch for the page's language: a button and its list, a popover below it (above everything, also the phone's
 * menu). Escape or a click outside closes the list. */
export function languageSwitch(doc: Document, reload: () => void = () => doc.defaultView!.location.reload()): HTMLElement {
  const current = doc.documentElement.lang;
  const label = `${t('Language')}: ${languageName(current)}`;
  const toggle = el('button', { type: 'button', class: 'icon-button language-toggle', popovertarget: 'language-list',
    'aria-label': `${current.toUpperCase()} – ${label}`, title: label }, current.toUpperCase());  // the code in the name: WCAG 2.5.3
  const list = el('div', { id: 'language-list', class: 'language-list', popover: 'auto' });
  for (const [code, name] of LANGUAGES) {
    const option = el('button', { type: 'button', lang: code, 'aria-current': code === current ? 'true' : null }, name);
    option.addEventListener('click', () => {
      api.saveLanguage(code).then(reload).catch(() => undefined);
    });
    list.append(option);
  }
  list.addEventListener('beforetoggle', () => {  // below the button, towards the side with room (left on phones)
    const button = toggle.getBoundingClientRect();
    const width = doc.documentElement.clientWidth;
    const rightHalf = button.left + button.width / 2 > width / 2;
    list.style.top = `${button.bottom + 8}px`;
    list.style.left = rightHalf ? 'auto' : `${button.left}px`;
    list.style.right = rightHalf ? `${width - button.right}px` : 'auto';
  });
  return el('div', { class: 'language-switch' }, toggle, list);
}
