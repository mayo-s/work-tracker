// The color theme: shown at once on <html>, and the dark mode switch in the header.

import { api, type Theme } from './api.ts';
import { el } from './dom.ts';

const ICON = 'viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" '
  + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
const MOON = `<svg ${ICON}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`;
const SUN = `<svg ${ICON}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4`
  + `M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`;

/** Shows a theme at once: `data-theme` on <html>, none for `system` (then the system setting decides). */
export function applyTheme(root: HTMLElement, theme: Theme): void {
  if (theme === 'system') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
}

/** The theme shown: the chosen one, or the system's while System is chosen. */
export function shownTheme(root: HTMLElement, systemDark: boolean): 'light' | 'dark' {
  const theme = root.dataset.theme;
  if (theme === 'light' || theme === 'dark') {
    return theme;
  }
  return systemDark ? 'dark' : 'light';
}

/** The dark mode switch: a moon in light mode, a sun in dark mode. A click turns to the other one and saves it as the
 * theme (from System it becomes Light or Dark; back if saving fails). It follows the theme when that changes
 * elsewhere (the settings, the system). */
export function themeToggle(doc: Document): HTMLButtonElement {
  const root = doc.documentElement;
  const system = doc.defaultView!.matchMedia('(prefers-color-scheme: dark)');
  const toggle = el('button', { type: 'button', class: 'button-small theme-toggle', 'aria-label': 'Dark mode',
    title: 'Dark mode' });
  const show = (): void => {
    const dark = shownTheme(root, system.matches) === 'dark';
    toggle.setAttribute('aria-pressed', String(dark));
    toggle.innerHTML = dark ? SUN : MOON;
  };
  toggle.addEventListener('click', () => {
    const before = (root.dataset.theme ?? 'system') as Theme;
    const theme = shownTheme(root, system.matches) === 'dark' ? 'light' : 'dark';
    applyTheme(root, theme);
    for (const radio of doc.querySelectorAll<HTMLInputElement>('input[name="theme"]')) {  // the settings' choice
      radio.checked = radio.value === theme;
    }
    api.saveTheme(theme).catch(() => applyTheme(root, before));
  });
  new MutationObserver(show).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  system.addEventListener('change', show);
  show();
  return toggle;
}
