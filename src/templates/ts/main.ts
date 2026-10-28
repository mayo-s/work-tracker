// Entry point of the frontend: loaded as an ES module by every page.
// Modules import each other with the compiled extension, e.g. `import { api } from './api.ts'`.

export const APP_NAME = 'Work Tracker';

/** Marks the navigation link of the current page, e.g. `/` for the week page. */
export function markCurrentPage(nav: ParentNode, path: string): void {
  for (const link of nav.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    if (link.getAttribute('href') === path) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }
}

/** Page code, loaded only on its page (`<main data-page="…">`). */
const PAGES: Record<string, () => Promise<void>> = {
  components: async () => (await import('./gallery.ts')).renderGallery(document),
  week: async () => (await import('./week.ts')).renderWeekPage(document),
};

const nav = document.querySelector('.app-nav');
if (nav) {
  markCurrentPage(nav, window.location.pathname);
}

const page = document.querySelector<HTMLElement>('#app')?.dataset.page;
if (page && page in PAGES) {
  await PAGES[page]?.();
}
