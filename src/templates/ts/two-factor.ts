// Two-factor page (/2fa): root and admins set up two-factor login before anything else; then on to their start page.

import { setupButton } from './account.ts';
import { api } from './api.ts';
import { el } from './dom.ts';

export async function renderTwoFactorPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#two-factor');
  if (!root) {
    return;
  }
  if ((await api.twoFactor()).enabled) {
    window.location.assign('/');
    return;
  }
  const part = el('div', { class: 'card login-form' }, el('p', {}, 'You need an authenticator app on your phone, e.g. Google '
    + 'Authenticator, Microsoft Authenticator or 1Password.'));
  part.append(setupButton(part, () => window.location.assign('/')));
  root.replaceChildren(part);
}
