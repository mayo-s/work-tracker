// The audit log (SPEC 5.7) as text: on the admin page all of it, in the settings the changes to the own account.

import type { AuditView } from './api.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { el } from './dom.ts';

const ROLE_NAMES: Record<string, string> = {
  admin: 'an admin', user: 'a user', team_admin: 'team admin', member: 'a member',
};

/** One entry as a sentence, e.g. `Pascal Turbo made Hans Dampf an admin`. */
export function auditText(entry: AuditView): string {
  const { actor, user, team, detail } = entry;
  const texts: Record<AuditView['action'], () => string> = {
    root_created: () => `${actor} became root`,
    role_changed: () => `${actor} made ${user} ${ROLE_NAMES[detail] ?? detail}`,
    team_role_changed: () => `${actor} made ${user} ${ROLE_NAMES[detail] ?? detail} of ${team}`,
    deactivated: () => `${actor} deactivated ${user}`,
    reactivated: () => `${actor} reactivated ${user}`,
    one_time_password: () => `${actor} set a one-time password for ${user}`,
    registration_switched: () => `${actor} switched registration ${detail}`,
    team_created: () => `${actor} created the team ${team}`,
    team_renamed: () => `${actor} renamed the team ${detail} to ${team}`,
    team_deleted: () => `${actor} deleted the team ${team}`,
    member_removed: () => `${actor} removed ${user} from ${team}`,
    auditor_assigned: () => `${actor} made ${user} auditor of ${team}${detail ? ` until ${formatDate(detail)}` : ''}`,
    auditor_removed: () => `${actor} ended ${user}'s audit of ${team}`,
  };
  return texts[entry.action]();
}

/** The entries as a table (When, What), or `empty` without any. */
export function auditTable(entries: AuditView[], empty: string): HTMLElement {
  if (!entries.length) {
    return el('p', {}, empty);
  }
  return el('table', { class: 'review-table list-table' },
    el('thead', {}, el('tr', {}, el('th', {}, 'When'), el('th', {}, 'What'))),
    el('tbody', {}, ...entries.map((entry) => el('tr', {},
      el('td', {}, formatTimestamp(entry.at)), el('td', {}, auditText(entry))))));
}
