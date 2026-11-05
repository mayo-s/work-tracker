// Entry point of the frontend: loaded as an ES module by every page.
// Modules import each other with the compiled extension, e.g. `import { api } from './api.ts'`.

export const APP_NAME = 'Work Tracker';

/** Marks the navigation link of the current page, e.g. `/week` (also with a query like `/week?member=…`). */
export function markCurrentPage(nav: ParentNode, path: string): void {
  for (const link of nav.querySelectorAll<HTMLAnchorElement>('a[href]')) {
    if (link.getAttribute('href')?.split(/[?#]/)[0] === path) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }
}

const TRACKING_LINKS = ['/', '/week', '/month', '/year', '/review'].map((href) => `a[href="${href}"]`).join(', ');

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
  password: async () => (await import('./password.ts')).renderPasswordPage(document),
  'two-factor': async () => (await import('./two-factor.ts')).renderTwoFactorPage(document),
  login: async () => (await import('./account.ts')).renderLoginPage(document),
  register: async () => (await import('./account.ts')).renderRegisterPage(document),
  admin: async () => (await import('./admin.ts')).renderAdminPage(document),
  team: async () => (await import('./team.ts')).renderTeamPage(document),
};

/** Shows the number of open review items next to the Review link; the review page keeps it up to date itself. */
async function showReviewCount(): Promise<void> {
  const { api } = await import('./api.ts');
  const { showReviewBadge } = await import('./review.ts');
  showReviewBadge(document, await api.reviewCounts());
}

/** The right end of the header: the user's name (`showUser`), the dark mode switch, then "Log out". Both load side
 * by side, so the switch goes before "Log out" if that is there already, and the name goes first. */
function headerEnd(header: Element): Element {
  const end = Object.assign(document.createElement('div'), { className: 'app-user' });
  header.append(end);
  import('./theme.ts').then(({ themeToggle }) => {
    const toggle = themeToggle(document);
    const logout = end.querySelector('button');
    if (logout) {
      logout.before(toggle);
    } else {
      end.append(toggle);
    }
  }).catch(() => undefined);
  return end;
}

/** The logged-in user's first name and "Log out" in the header (nothing when the login is off). With `nav`, also the
 * Team link for team admins, the Admin link for admins, and a badge on Settings for open team invitations; without it
 * (the setup page) only name and "Log out": a new user can leave and finds the setup again after the next login. */
async function showUser(user: Element, nav: Element | null): Promise<void> {
  const { api } = await import('./api.ts');
  const status = await api.authStatus();
  if (!status.enabled || !status.user) {
    return;
  }
  const logout = Object.assign(document.createElement('button'), { type: 'button', className: 'button-small',
    textContent: 'Log out' });
  logout.addEventListener('click', () => void api.logout().then(() => window.location.assign('/login')));
  const name = Object.assign(document.createElement('span'), { className: 'muted', textContent: status.user.first_name });
  user.prepend(name);
  user.append(logout);
  if (!nav) {
    return;
  }
  if (status.user.role === 'root') {  // root tracks no work
    nav.querySelectorAll(TRACKING_LINKS).forEach((link) => link.remove());
  }
  if (status.team?.team_role === 'team_admin') {
    nav.append(Object.assign(document.createElement('a'), { href: '/team', textContent: 'Team' }));
  }
  if (status.user.role === 'admin' || status.user.role === 'root') {
    nav.append(Object.assign(document.createElement('a'), { href: '/admin', textContent: 'Admin' }));
  }
  markCurrentPage(nav, window.location.pathname);
  if (status.invitations) {  // open team invitations wait in the settings
    nav.querySelector('a[href="/settings"]')?.append(' ', Object.assign(document.createElement('span'), {
      className: 'badge warning', textContent: String(status.invitations), title: 'Open team invitations',
    }));
  }
}

const page = document.querySelector<HTMLElement>('#app')?.dataset.page;
const nav = document.querySelector('.app-nav');
if (nav && !['login', 'register', 'setup', 'password', 'two-factor'].includes(page ?? '')) {
  markCurrentPage(nav, window.location.pathname);
  if (page !== 'review') {
    showReviewCount().catch(() => undefined);  // the count is a hint; pages work without it
  }
  showUser(headerEnd(document.querySelector('.app-header')!), nav).catch(() => undefined);
}
if (['setup', 'password', 'two-factor'].includes(page ?? '')) {  // still to do first: still able to log out
  showUser(headerEnd(document.querySelector('.app-header')!), null).catch(() => undefined);
}

const member = new URLSearchParams(window.location.search).get('member');
if (member && ['dashboard', 'week', 'month', 'year'].includes(page ?? '')) {
  const { showTeamView } = await import('./team-view.ts');
  showTeamView(document, member).catch(() => undefined);  // the banner is a hint; the page shows the data anyway
}

if (page && page in PAGES) {
  await PAGES[page]?.();
}
