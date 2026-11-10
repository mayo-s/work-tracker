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
  search: async () => (await import('./search.ts')).renderSearchPage(document),
  settings: async () => (await import('./settings.ts')).renderSettingsPage(document),
  setup: async () => (await import('./setup.ts')).renderSetupPage(document),
  password: async () => (await import('./password.ts')).renderPasswordPage(document),
  'two-factor': async () => (await import('./two-factor.ts')).renderTwoFactorPage(document),
  login: async () => (await import('./account.ts')).renderLoginPage(document),
  register: async () => (await import('./account.ts')).renderRegisterPage(document),
  admin: async () => (await import('./admin.ts')).renderAdminPage(document),
  team: async () => (await import('./team.ts')).renderTeamPage(document),
  'team-report': async () => (await import('./team-report.ts')).renderTeamReportPage(document),
  imprint: async () => (await import('./imprint.ts')).renderImprintPage(document),
  privacy: async () => (await import('./privacy.ts')).renderPrivacyPage(document),
  contact: async () => (await import('./contact.ts')).renderContactPage(document),
  support: async () => (await import('./support.ts')).renderSupportPage(document),
};

/** Shows the Review link with the number of open review items while there are any (SPEC 5.4); the review page shows
 * the link anyway and keeps the count up to date itself. */
async function showReviewCount(): Promise<void> {
  const { api } = await import('./api.ts');
  const { showReviewBadge } = await import('./review.ts');
  showReviewBadge(document, await api.reviewCounts());
}

/** The right end of the header: the search field (in the frame), the user's name (`showUser`), the dark mode switch,
 * then the menu (in the frame) or, on the pages that come first, "Log out". Both load side by side, so the switch goes
 * before the shown menu or "Log out" if that is there already. */
function headerEnd(header: Element): Element {
  const end = header.querySelector('.app-user')!;
  import('./theme.ts').then(({ themeToggle }) => {
    const toggle = themeToggle(document);
    const after = end.querySelector('.account-menu:not([hidden]), .logout');
    if (after) {
      after.before(toggle);
    } else {
      end.append(toggle);
    }
  }).catch(() => undefined);
  return end;
}

function navLink(href: string, textContent: string): HTMLAnchorElement {
  return Object.assign(document.createElement('a'), { href, textContent });
}

function badge(count: number, title: string): HTMLElement {
  return Object.assign(document.createElement('span'), { className: 'badge warning', textContent: String(count), title });
}

/** What waits behind ☰, for its label: e.g. `Menu, 1 open team invitation, 2 new contact messages`. */
function menuLabel(invitations: number, newMessages: number): string {
  const waiting: [number, string][] = [[invitations, 'open team invitation'], [newMessages, 'new contact message']];
  return ['Menu', ...waiting.filter(([count]) => count).map(([count, what]) => `${count} ${what}${count > 1 ? 's' : ''}`)]
    .join(', ');
}

/** The menu (☰) at the right end of the header (SPEC 5.5): a panel with Team, Settings, Admin and "Log out" below it,
 * shown on the pages with navigation. Escape or a click outside closes it and, with Escape, gives the focus back to ☰.
 * On phones its entries are listed directly in the phone's menu (CSS). */
export function setUpAccountMenu(menu: HTMLElement): void {
  const toggle = menu.querySelector<HTMLButtonElement>('.account-toggle')!;
  const open = (opened: boolean): void => toggle.setAttribute('aria-expanded', String(opened));
  menu.hidden = false;
  toggle.addEventListener('click', () => open(toggle.getAttribute('aria-expanded') !== 'true'));
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      event.stopPropagation();  // not the phone's menu around it as well
      open(false);
      toggle.focus();
    }
  });
  document.addEventListener('click', (event) => {
    if (!menu.contains(event.target as Node)) {
      open(false);
    }
  });
}

/** The logged-in user's first name in the header (nothing when the login is off). With `nav`, also the Audit tab (the
 * team report) after Year for team admins and auditors, and in the menu the Team link and the Support link before
 * Settings for team admins and support, the Admin link after it for admins, "Log out" last, and badges on Settings for
 * open team invitations, on Support for new contact messages and on ☰ for both together; without
 * it (the pages that come first) name and "Log out": a new user can leave and finds the setup again after the next
 * login. */
async function showUser(user: Element, nav: Element | null): Promise<void> {
  const { api } = await import('./api.ts');
  const status = await api.authStatus();
  if (!status.enabled || !status.user) {
    return;
  }
  const logout = Object.assign(document.createElement('button'), { type: 'button', className: 'button-small logout',
    textContent: 'Log out' });
  logout.addEventListener('click', () => void api.logout().then(() => window.location.assign('/login')));
  const name = Object.assign(document.createElement('span'), { className: 'muted', textContent: status.user.first_name });
  const search = user.querySelector('.nav-search');
  if (search) {
    search.after(name);
  } else {
    user.prepend(name);
  }
  const links = user.querySelector('.account-links');
  if (!nav || !links) {
    user.append(logout);
    return;
  }
  links.append(logout);
  if (status.user.role === 'root') {  // root tracks no work
    nav.querySelectorAll(TRACKING_LINKS).forEach((link) => link.remove());
    user.querySelector('.nav-search')?.remove();
  }
  const settings = links.querySelector('a[href="/settings"]')!;
  if (status.team?.team_role === 'team_admin') {
    settings.before(navLink('/team', 'Team'));
  }
  if (status.user.support) {
    const support = navLink('/support', 'Support');
    settings.before(support);
    if (status.new_messages) {
      support.append(' ', badge(status.new_messages, 'New contact messages'));
    }
  }
  if (status.team?.team_role === 'team_admin' || status.auditor) {
    nav.querySelector('a[href^="/year"]')?.after(navLink('/team/report', 'Audit'));  // the team view adds the member to it
  }
  if (status.user.role === 'admin' || status.user.role === 'root') {
    settings.after(navLink('/admin', 'Admin'));
  }
  markCurrentPage(nav, window.location.pathname);
  markCurrentPage(links, window.location.pathname);
  if (status.invitations) {  // open team invitations wait in the settings
    settings.append(' ', badge(status.invitations, 'Open team invitations'));
  }
  const [invitations, newMessages] = [status.invitations ?? 0, status.new_messages ?? 0];
  if (invitations + newMessages) {
    const toggle = user.querySelector('.account-toggle')!;
    toggle.append(badge(invitations + newMessages, 'Open team invitations and new contact messages'));
    toggle.setAttribute('aria-label', menuLabel(invitations, newMessages));
  }
}

/** The header's menu on phones (SPEC 5.5a): the button shows and hides the navigation, search and user below the
 * header; Escape closes it and gives the focus back to the button. Wider screens show them in the header and no button
 * (CSS). */
export function setUpMenu(header: Element): void {
  const toggle = header.querySelector<HTMLButtonElement>('.menu-toggle');
  if (!toggle) {
    return;
  }
  const open = (opened: boolean): void => toggle.setAttribute('aria-expanded', String(opened));
  toggle.addEventListener('click', () => open(toggle.getAttribute('aria-expanded') !== 'true'));
  header.addEventListener('keydown', (event) => {
    if ((event as KeyboardEvent).key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      open(false);
      toggle.focus();
    }
  });
}

const page = document.querySelector<HTMLElement>('#app')?.dataset.page;
const nav = document.querySelector('.app-nav');
if (nav && !['login', 'register', 'setup', 'password', 'two-factor', 'imprint', 'privacy', 'contact']
  .includes(page ?? '')) {
  setUpMenu(document.querySelector('.app-header')!);
  setUpAccountMenu(document.querySelector<HTMLElement>('.account-menu')!);
  markCurrentPage(nav, window.location.pathname);
  if (page === 'review') {
    nav.querySelector<HTMLElement>('a[href="/review"]')!.hidden = false;
  } else {
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
