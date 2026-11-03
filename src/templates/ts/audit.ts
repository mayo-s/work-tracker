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
    root_login_reset: () => `${actor} reset the root login with a new setup token`,
    role_changed: () => `${actor} made ${user} ${ROLE_NAMES[detail] ?? detail}`,
    team_role_changed: () => `${actor} made ${user} ${ROLE_NAMES[detail] ?? detail} of ${team}`,
    deactivated: () => `${actor} deactivated ${user}`,
    reactivated: () => `${actor} reactivated ${user}`,
    one_time_password: () => `${actor} set a one-time password for ${user}`,
    two_factor_reset: () => `${actor} reset the two-factor login of ${user}`,
    password_changed: () => (detail === 'command' ? `The password of ${user} was set with the set-password command`
      : `${actor} changed their password`),
    two_factor_on: () => `${actor} switched two-factor login on`,
    two_factor_off: () => `${actor} switched two-factor login off`,
    two_factor_new_app: () => `${actor} moved two-factor login to a new authenticator app`,
    recovery_codes_renewed: () => `${actor} made new recovery codes`,
    backup_made: () => `${actor} downloaded a full backup`,
    backup_restored: () => `${actor} restored a full backup`,
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
