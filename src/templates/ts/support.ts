// Support page (/support): the messages of the contact page and their archive, with search; a message opens with its
// whole text, status, internal notes, "Answer by e-mail" and its changes (SPEC 5.14). For support users only.

import { api, type MessageStatus, type MessageView } from './api.ts';
import { formatTimestamp } from './dates.ts';
import { ask } from './dialog.ts';
import { button, el, scrolling } from './dom.ts';
import { renderEditablePage, type Page } from './editable-table.ts';
import { field, submit } from './forms.ts';
import { t } from './i18n.ts';

export const STATUS_LABELS: Record<MessageStatus, string> = { new: t('New'), in_progress: t('In progress'), done: t('Done') };
const STATUS_BADGES: Record<MessageStatus, string> = { new: 'badge warning', in_progress: 'badge', done: 'badge positive' };

/** Whether a logged-in user sent it; kept in the archive. */
export function senderLabel(message: MessageView): string {
  return message.known ? t('Known user') : t('Unknown user');
}

/** Opens the own mail program with the address and "Re: <subject>" filled in; the app sends no e-mails. */
export function answerLink(message: MessageView): string {
  return `mailto:${message.email}?subject=${encodeURIComponent(`Re: ${message.subject}`)}`;
}

/** A change as text: the new status, or the note. */
export function describeChange(change: MessageView['changes'][number]): string {
  return change.kind === 'status'
    ? t('Status: {status}', { status: STATUS_LABELS[change.detail as MessageStatus] ?? change.detail })
    : t('Note: {text}', { text: change.detail });
}

function messageLink(message: MessageView): string {
  return `/support?${new URLSearchParams({ message: message.id })}`;
}

function sender(message: MessageView): HTMLElement {
  return el('span', {}, message.name, message.username ? el('span', { class: 'muted' }, ` (${message.username})`) : null,
    ' ', el('span', { class: message.known ? 'badge positive' : 'badge' }, senderLabel(message)));
}

function statusBadge(status: MessageStatus): HTMLElement {
  return el('span', { class: STATUS_BADGES[status] }, STATUS_LABELS[status]);
}

function messagesTable(messages: MessageView[], empty: string): HTMLElement {
  if (!messages.length) {
    return el('p', { class: 'muted' }, empty);
  }
  const header = el('tr', {}, ...[t('Sent'), t('From'), t('Subject'), t('Status')].map((label) => el('th', {}, label)));
  return scrolling(el('table', { class: 'review-table list-table support-messages' }, el('thead', {}, header),
    el('tbody', {}, ...messages.map((message) => el('tr', {},
      el('td', {}, el('span', { class: 'num' }, formatTimestamp(message.sent_at))),
      el('td', {}, sender(message)),
      el('td', {}, el('a', { href: messageLink(message) }, message.subject)),
      el('td', {}, statusBadge(message.status)))))));
}

function searchForm(text: string): HTMLFormElement {
  return el('form', { class: 'support-search', role: 'search', action: '/support' },
    el('input', { type: 'search', name: 'text', value: text, maxlength: 200, 'aria-label': t('Search messages'),
      placeholder: t('Words in subject, message or notes') }),
    el('button', { type: 'submit' }, t('Search')),
    text ? el('a', { href: '/support' }, t('Show all')) : null);
}

async function listView(text: string): Promise<HTMLElement[]> {
  const found = await api.supportMessages(text);
  const none = text ? t('None match the search.') : null;
  return [searchForm(text),
    el('section', { class: 'review-section', id: 'messages' },
      el('h2', {}, t('Messages')),
      el('p', { class: 'muted' }, t('The open ones and the done ones of the last 90 days, newest first.')),
      messagesTable(found.messages, none ?? t('No messages.'))),
    el('section', { class: 'review-section', id: 'archive' },
      el('h2', {}, t('Archive')),
      el('p', { class: 'muted' },
        t('Done for 90 days: the sender is a color and an animal, without e-mail address; subject, message and notes stay.')),
      messagesTable(found.archive, none ?? t('Nothing archived yet.')))];
}

function statusSelect(message: MessageView, page: Page): HTMLElement {
  const select = el('select', { id: 'message-status' }, ...Object.entries(STATUS_LABELS).map(([value, label]) =>
    el('option', { value, selected: value === message.status }, label)));
  select.addEventListener('change', () => {
    const status = select.value as MessageStatus;
    api.setMessageStatus(message.id, status)
      .then(() => page.reload(t('Marked as {status}', { status: STATUS_LABELS[status] })), page.fail);
  });
  return el('div', { class: 'field' }, el('label', { for: 'message-status' }, t('Status')), select);
}

function noteForm(message: MessageView, page: Page): HTMLFormElement {
  const text = el('textarea', { id: 'note-text', name: 'text', maxlength: 5000, rows: 3 });
  const form = el('form', { class: 'support-note', novalidate: true },
    field('note', 'text', t('Internal note'), text, t('Only support sees it.')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit' }, t('Add note'))));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void submit(form, 'note', ['text'], () => api.addMessageNote(message.id, text.value),
      () => page.reload(t('Added the note')));
  });
  return form;
}

function deleteButton(message: MessageView, page: Page): HTMLButtonElement {
  return button(t('Delete'), () => {
    void ask(t('Delete "{subject}"?', { subject: message.subject }), [t('The message and its notes are gone for good.')],
      [{ label: t('Delete'), value: true, primary: true }]).then((yes) => {
      if (yes) {
        api.deleteMessage(message.id).then(() => {
          window.history.replaceState(null, '', '/support');
          page.reload(t('Deleted "{subject}"', { subject: message.subject }));
        }, page.fail);
      }
    });
  }, { class: null });
}

function history(message: MessageView): HTMLElement {
  if (!message.changes.length) {
    return el('p', { class: 'muted' }, t('No changes yet.'));
  }
  return el('ol', { class: 'history-list' }, ...message.changes.map((change) => el('li', {},
    el('span', { class: 'num muted' }, formatTimestamp(change.at)), ' ', el('strong', {}, change.actor), ' ',
    el('span', { class: 'message-text' }, describeChange(change)))));
}

async function messageView(id: string, page: Page): Promise<HTMLElement[]> {
  const message = await api.supportMessage(id);
  const details: [string, string | HTMLElement][] = [[t('From'), sender(message)], [t('E-mail address'), message.email || '—'],
    [t('Sent'), formatTimestamp(message.sent_at)], [t('Status'), statusBadge(message.status)]];
  const actions = message.archived
    ? [el('p', { class: 'muted' }, t('Archived: it stays as it is.')),
      el('div', { class: 'form-actions' }, deleteButton(message, page))]
    : [el('div', { class: 'form-actions' },
      el('a', { class: 'button primary', href: answerLink(message) }, t('Answer by e-mail')), deleteButton(message, page)),
    statusSelect(message, page), noteForm(message, page)];
  return [el('p', {}, el('a', { href: '/support' }, t('← All messages'))),
    el('section', { class: 'review-section support-message' },
      el('h2', {}, message.subject),
      el('dl', { class: 'details-list' }, ...details.flatMap(([label, value]) => [el('dt', {}, label), el('dd', {}, value)])),
      el('p', { class: 'message-text' }, message.text),
      ...actions),
    el('section', { class: 'review-section' }, el('h2', {}, t('History')), history(message))];
}

export async function renderSupportPage(doc: Document): Promise<void> {
  await renderEditablePage(doc, 'support', 'support-status', (page) => {
    const params = new URLSearchParams(doc.location.search);
    const id = params.get('message');
    return id ? messageView(id, page) : listView(params.get('text') ?? '');
  });
}
