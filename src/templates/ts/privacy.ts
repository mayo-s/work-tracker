// Privacy policy page (/privacy): what personal data the app keeps, why and for how long (GDPR Art. 13); in German or
// a translation, open to everyone like the imprint, whose details name the controller (SPEC 5.15). The rest of the text
// is in the page.

import { api, ApiError } from './api.ts';
import { el } from './dom.ts';
import { legalTexts } from './legal.ts';

export async function renderPrivacyPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#privacy-controller');
  if (!root) {
    return;
  }
  const texts = legalTexts(root);
  try {
    const details = await api.imprint();
    root.replaceChildren(
      el('p', {}, details.name, el('br'), details.street, el('br'), details.city, el('br'), details.country),
      el('p', {}, `${texts.email}: `, el('a', { href: `mailto:${details.email}` }, details.email), el('br'),
        el('a', { href: '/contact' }, texts.contactForm), el('br'), el('a', { href: '/imprint' }, texts.imprint)),
    );
  } catch (error) {
    root.replaceChildren(el('p', { class: 'muted' }, error instanceof ApiError && error.status === 404
      ? texts.controllerMissing : texts.controllerFailed));
  }
}
