// Contact page (/contact): anyone writes to the people running the app, who answer by e-mail (SPEC 5.14); open to
// everyone, like the imprint that links to it.

import { EMAIL } from './account.ts';
import { api, ApiError, type ContactInput } from './api.ts';
import { el } from './dom.ts';
import { field, submit } from './forms.ts';

const FIELDS = ['name', 'email', 'subject', 'text'] as const;
export const THANKS = 'Thanks, we will answer by e-mail.';

/** What is missing or wrong, as errors under the fields in the form of the API's (which checks the same, in its own
 * words). */
export function contactProblems(input: ContactInput): { loc: string[]; msg: string }[] {
  const problems: [string, boolean, string][] = [
    ['name', !input.name.trim(), 'Enter your name.'],
    ['email', !EMAIL.test(input.email.trim()), 'Enter an e-mail address like name@example.com.'],
    ['subject', !input.subject.trim(), 'Enter a subject.'],
    ['text', !input.text.trim(), 'Enter your message.'],
  ];
  return problems.filter(([, wrong]) => wrong).map(([name, , msg]) => ({ loc: [name], msg }));
}

function send(input: ContactInput): Promise<void> {
  const problems = contactProblems(input);
  return problems.length ? Promise.reject(new ApiError(422, problems[0]!.msg, problems)) : api.sendMessage(input);
}

export async function renderContactPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#contact');
  if (!root) {
    return;
  }
  const name = el('input', { id: 'contact-name', name: 'name', maxlength: 100, autocomplete: 'name' });
  const email = el('input', { id: 'contact-email', name: 'email', type: 'email', maxlength: 200, autocomplete: 'email' });
  const subject = el('input', { id: 'contact-subject', name: 'subject', maxlength: 200 });
  const text = el('textarea', { id: 'contact-text', name: 'text', maxlength: 5000, rows: 8 });
  const website = el('input', { name: 'website', tabindex: -1, autocomplete: 'off' });  // a trap for bots, hidden from people
  const form = el('form', { class: 'login-form', novalidate: true },
    field('contact', 'name', 'Name', name),
    field('contact', 'email', 'E-mail address', email, 'Where support answers.'),
    field('contact', 'subject', 'Subject', subject),
    field('contact', 'text', 'Message', text, 'Up to 5,000 characters.'),
    el('div', { class: 'contact-trap', 'aria-hidden': 'true' }, el('label', {}, 'Website ', website)),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Send')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'contact', FIELDS, () => send({
      name: name.value, email: email.value, subject: subject.value, text: text.value, website: website.value,
    }), () => root.replaceChildren(el('p', { role: 'status' }, THANKS)));
  });
  root.replaceChildren(form);
  const user = (await api.authStatus().catch(() => null))?.user;  // a logged-in user's name and address are filled in
  if (user) {
    name.value ||= [user.first_name, user.last_name].filter(Boolean).join(' ');
    email.value ||= user.email;
  }
}
