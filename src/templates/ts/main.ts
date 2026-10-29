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
  login: async () => (await import('./account.ts')).renderLoginPage(document),
  register: async () => (await import('./account.ts')).renderRegisterPage(document),
  admin: async () => (await import('./admin.ts')).renderAdminPage(document),
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

/** The logged-in user's first name and "Log out" in the header, and for admins the Admin link (nothing when the login
 * is off). */
async function showUser(header: Element, nav: Element): Promise<void> {
  const { api } = await import('./api.ts');
  const status = await api.authStatus();
  if (!status.enabled || !status.user) {
    return;
  }
  if (status.user.role === 'admin') {
    nav.append(Object.assign(document.createElement('a'), { href: '/admin', textContent: 'Admin' }));
    markCurrentPage(nav, window.location.pathname);
  }
  const logout = Object.assign(document.createElement('button'), { type: 'button', className: 'button-small',
    textContent: 'Log out' });
  logout.addEventListener('click', () => void api.logout().then(() => window.location.assign('/login')));
  const user = Object.assign(document.createElement('div'), { className: 'app-user' });
  const name = Object.assign(document.createElement('span'), { className: 'muted', textContent: status.user.first_name });
  user.append(name, logout);
  header.append(user);
}

const page = document.querySelector<HTMLElement>('#app')?.dataset.page;
const nav = document.querySelector('.app-nav');
if (nav && !['login', 'register', 'setup'].includes(page ?? '')) {
  markCurrentPage(nav, window.location.pathname);
  showReviewCount(nav).catch(() => undefined);  // the count is a hint; pages work without it
  showUser(document.querySelector('.app-header')!, nav).catch(() => undefined);
}

if (page && page in PAGES) {
  await PAGES[page]?.();
}
