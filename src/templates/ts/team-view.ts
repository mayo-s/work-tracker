// Team view: a team admin looks at a member's dashboard, week, month and year, read-only (`?member=<id>`).

import { api, type MemberView } from './api.ts';
import { formatDate } from './dates.ts';
import { el } from './dom.ts';

/** The pages of the team view; links to them keep the member. */
export const TEAM_VIEW_PAGES = ['/', '/week', '/month', '/year'];
const OWN_VIEW = 'data-own-view';

/** The member being viewed, or null for the user's own data. */
export function viewedMember(search: string): string | null {
  return new URLSearchParams(search).get('member') || null;
}

/** A link to a page of the team view with the member kept, e.g. `/month?month=2026-10&member=…`; others unchanged. */
export function withMember(href: string, member: string): string {
  const url = new URL(href, 'http://app');
  if (url.host !== 'app' || !TEAM_VIEW_PAGES.includes(url.pathname) || url.searchParams.get('member') === member) {
    return href;
  }
  url.searchParams.set('member', member);
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The same page without the member: the user's own data. */
export function ownView(path: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete('member');
  return params.size ? `${path}?${params}` : path;
}

export function fullName(member: MemberView): string {
  return [member.first_name, member.last_name].filter(Boolean).join(' ');
}

/** Keeps the member in all links to the team view pages, also in those the page renders later. */
function keepMember(root: Node & ParentNode, member: string): void {
  const update = (): void => {
    for (const link of root.querySelectorAll<HTMLAnchorElement>(`a[href]:not([${OWN_VIEW}])`)) {
      const href = link.getAttribute('href')!;
      const kept = withMember(href, member);
      if (kept !== href) {
        link.setAttribute('href', kept);
      }
    }
  };
  update();
  new MutationObserver(update).observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['href'] });
}

/** The banner of the team view on top of the page, and the member kept in the links. */
export async function showTeamView(doc: Document, member: string): Promise<void> {
  keepMember(doc.body, member);
  const status = await api.authStatus();
  const team = status.team ? await api.team(status.team.id) : null;
  const viewed = team?.members.find((item) => item.user_id === member);
  const since = viewed && team ? ` from ${formatDate(viewed.joined_on)}, when they joined ${team.name}` : '';
  doc.querySelector('main')?.prepend(el('div', { class: 'card team-view-banner', role: 'status' },
    'Read-only: ', el('strong', {}, `${viewed ? fullName(viewed) : 'A member'}'s data`), `${since}. `,
    'The overtime balance and PTO left cover the whole time. ',
    el('a', { href: ownView(doc.location.pathname, doc.location.search), [OWN_VIEW]: true }, 'Back to your data')));
}
