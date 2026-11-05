// Two-factor page (/2fa): root and admins set up two-factor login before anything else; then on to their start page.
// Root alone in a new database may restore a full backup instead.

import { setupButton } from './account.ts';
import { api } from './api.ts';
import { el } from './dom.ts';

export async function renderTwoFactorPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#two-factor');
  if (!root) {
    return;
  }
  const status = await api.twoFactor();
  if (status.enabled) {
    window.location.assign('/');
    return;
  }
  const part = el('div', { class: 'card login-form' }, el('p', {}, 'You need an authenticator app on your phone, e.g. Google '
    + 'Authenticator, Microsoft Authenticator or 1Password.'));
  part.append(setupButton(part, () => window.location.assign('/')));
  root.replaceChildren(part);
  if (status.restore_instead) {
    root.append(await restoreCard());
  }
}

/** Root alone in a new database restores the full backup of another Work Tracker instead: its root login comes with
 * its own two-factor login. */
async function restoreCard(): Promise<HTMLElement> {
  const { restoreForm } = await import('./admin.ts');
  return el('section', { class: 'card login-form', id: 'restore' },
    el('h2', {}, 'Or restore a full backup'),
    el('p', { class: 'muted' }, 'Moving from another Work Tracker? Restore its full backup instead: you take over its '
      + 'root login (username, password and two-factor login) and log in again with it.'),
    restoreForm(false, null));
}
