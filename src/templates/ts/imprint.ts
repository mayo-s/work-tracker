// Imprint page (/imprint): who runs the app, as German law requires (§ 5 DDG); in German or a translation, open to
// everyone (SPEC 5.13).

import { api, ApiError } from './api.ts';
import { el } from './dom.ts';
import { legalTexts } from './legal.ts';

export async function renderImprintPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#imprint');
  if (!root) {
    return;
  }
  const texts = legalTexts(root);
  try {
    const details = await api.imprint();
    root.replaceChildren(
      el('h2', {}, texts.heading),
      el('p', {}, details.name, el('br'), details.street, el('br'), details.city, el('br'), details.country),
      el('h2', {}, texts.contact),
      el('p', {}, `${texts.email}: `, el('a', { href: `mailto:${details.email}` }, details.email), el('br'),
        el('a', { href: '/contact' }, texts.contactForm)),
    );
  } catch (error) {
    root.replaceChildren(el('p', { class: 'muted' }, error instanceof ApiError && error.status === 404
      ? texts.imprintMissing : texts.imprintFailed));
  }
}
