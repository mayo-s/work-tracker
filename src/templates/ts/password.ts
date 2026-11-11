// New password page (/password): after a one-time password from an admin, the user chooses their own before anything else.

import { passwordForm } from './account.ts';
import { t } from './i18n.ts';

export async function renderPasswordPage(doc: Document): Promise<void> {
  doc.querySelector('#password')?.replaceChildren(passwordForm(() => window.location.assign('/'), t('One-time password')));
}
