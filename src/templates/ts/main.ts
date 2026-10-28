// Entry point of the frontend: loaded as an ES module by every page.
// Modules import each other with the compiled extension, e.g. `import { api } from './api.js'`.

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

const nav = document.querySelector('.app-nav');
if (nav) {
  markCurrentPage(nav, window.location.pathname);
}
