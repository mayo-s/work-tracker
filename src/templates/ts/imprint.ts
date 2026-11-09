// Imprint page (/imprint): who runs the app, as German law requires (§ 5 DDG); in German, open to everyone (SPEC 5.13).

import { api, ApiError } from './api.ts';
import { el } from './dom.ts';

export async function renderImprintPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#imprint');
  if (!root) {
    return;
  }
  try {
    const details = await api.imprint();
    root.replaceChildren(
      el('h2', {}, 'Angaben gemäß § 5 DDG'),
      el('p', {}, details.name, el('br'), details.street, el('br'), details.city, el('br'), details.country),
      el('h2', {}, 'Kontakt'),
      el('p', {}, 'E-Mail: ', el('a', { href: `mailto:${details.email}` }, details.email)),
    );
  } catch (error) {
    root.replaceChildren(el('p', { class: 'muted' }, error instanceof ApiError && error.status === 404
      ? 'Das Impressum ist noch nicht eingerichtet.' : 'Das Impressum konnte nicht geladen werden.'));
  }
}
