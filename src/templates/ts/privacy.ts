// Privacy policy page (/privacy): what personal data the app keeps, why and for how long (GDPR Art. 13); in German,
// open to everyone like the imprint, whose details name the controller (SPEC 5.15). The rest of the text is in the page.

import { api, ApiError } from './api.ts';
import { el } from './dom.ts';

export async function renderPrivacyPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#privacy-controller');
  if (!root) {
    return;
  }
  try {
    const details = await api.imprint();
    root.replaceChildren(
      el('p', {}, details.name, el('br'), details.street, el('br'), details.city, el('br'), details.country),
      el('p', {}, 'E-Mail: ', el('a', { href: `mailto:${details.email}` }, details.email), el('br'),
        el('a', { href: '/contact' }, 'Kontaktformular'), el('br'), el('a', { href: '/imprint' }, 'Impressum')),
    );
  } catch (error) {
    root.replaceChildren(el('p', { class: 'muted' }, error instanceof ApiError && error.status === 404
      ? 'Der Verantwortliche ist noch nicht eingerichtet (siehe Impressum).'
      : 'Die Angaben zum Verantwortlichen konnten nicht geladen werden.'));
  }
}
