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
  dashboard: async () => (await import('./dashboard.ts')).renderDashboardPage(document),
  week: async () => (await import('./week.ts')).renderWeekPage(document),
  month: async () => (await import('./month.ts')).renderMonthPage(document),
  year: async () => (await import('./year.ts')).renderYearPage(document),
  review: async () => (await import('./review.ts')).renderReviewPage(document),
  settings: async () => (await import('./settings.ts')).renderSettingsPage(document),
  setup: async () => (await import('./setup.ts')).renderSetupPage(document),
};

/** Shows the number of open review items next to the Review link, as a warning badge. */
async function showReviewCount(nav: Element): Promise<void> {
  const link = nav.querySelector('a[href="/review"]');
  if (!link) {
    return;
  }
  const { api } = await import('./api.ts');
  const { reviewTotal } = await import('./review.ts');
  const total = reviewTotal((await api.review()).counts);
  if (total) {
    link.append(' ', Object.assign(document.createElement('span'), { className: 'badge warning', textContent: String(total) }));
  }
}

const nav = document.querySelector('.app-nav');
if (nav) {
  markCurrentPage(nav, window.location.pathname);
  showReviewCount(nav).catch(() => undefined);  // the count is a hint; pages work without it
}

const page = document.querySelector<HTMLElement>('#app')?.dataset.page;
if (page && page in PAGES) {
  await PAGES[page]?.();
}
