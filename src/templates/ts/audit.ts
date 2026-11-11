// The audit log (SPEC 5.7) as text: on the admin page all of it, in the settings the changes to the own account.

import type { AuditView } from './api.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { el, scrolling } from './dom.ts';
import { t } from './i18n.ts';

/** One entry as a sentence, e.g. `Pascal Turbo made Hans Dampf an admin`; whole sentences, as the word order differs
 * between languages. */
export function auditText(entry: AuditView): string {
  const { detail } = entry;
  const names = { actor: entry.actor, user: entry.user ?? '', team: entry.team ?? '' };
  const texts: Record<AuditView['action'], () => string> = {
    root_created: () => t('{actor} became root', names),
    root_login_reset: () => t('{actor} reset the root login with a new setup token', names),
    role_changed: () => (detail === 'admin' ? t('{actor} made {user} an admin', names)
      : t('{actor} made {user} a user', names)),
    team_role_changed: () => (detail === 'team_admin' ? t('{actor} made {user} team admin of {team}', names)
      : t('{actor} made {user} a member of {team}', names)),
    deactivated: () => t('{actor} deactivated {user}', names),
    reactivated: () => t('{actor} reactivated {user}', names),
    one_time_password: () => t('{actor} set a one-time password for {user}', names),
    two_factor_reset: () => t('{actor} reset the two-factor login of {user}', names),
    password_changed: () => (detail === 'command' ? t('The password of {user} was set with the set-password command', names)
      : t('{actor} changed their password', names)),
    two_factor_on: () => t('{actor} switched two-factor login on', names),
    two_factor_off: () => t('{actor} switched two-factor login off', names),
    two_factor_new_app: () => t('{actor} moved two-factor login to a new authenticator app', names),
    recovery_codes_renewed: () => t('{actor} made new recovery codes', names),
    backup_made: () => t('{actor} downloaded a full backup', names),
    backup_restored: () => (detail === 'root login' ? t('{actor} restored a full backup with its root login', names)
      : t('{actor} restored a full backup', names)),
    registration_switched: () => (detail === 'on' ? t('{actor} switched registration on', names)
      : t('{actor} switched registration off', names)),
    team_created: () => t('{actor} created the team {team}', names),
    team_renamed: () => t('{actor} renamed the team {former} to {team}', { ...names, former: detail }),
    team_deleted: () => t('{actor} deleted the team {team}', names),
    member_removed: () => t('{actor} removed {user} from {team}', names),
    auditor_assigned: () => (detail ? t('{actor} made {user} auditor of {team} until {date}', { ...names, date: formatDate(detail) })
      : t('{actor} made {user} auditor of {team}', names)),
    auditor_removed: () => t("{actor} ended {user}'s audit of {team}", names),
    support_switched: () => (detail === 'on' ? t('{actor} switched the support role of {user} on', names)
      : t('{actor} switched the support role of {user} off', names)),
    account_deleted: () => (detail === 'own' ? t('{actor} deleted their account', names)
      : t('{actor} deleted an account', names)),
  };
  return texts[entry.action]();
}

/** The entries as a table (When, What), or `empty` without any. */
export function auditTable(entries: AuditView[], empty: string): HTMLElement {
  if (!entries.length) {
    return el('p', {}, empty);
  }
  return scrolling(el('table', { class: 'review-table list-table' },
    el('thead', {}, el('tr', {}, el('th', {}, t('When')), el('th', {}, t('What')))),
    el('tbody', {}, ...entries.map((entry) => el('tr', {},
      el('td', {}, formatTimestamp(entry.at)), el('td', {}, auditText(entry)))))));
}
