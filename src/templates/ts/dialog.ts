// A modal question with buttons: a native <dialog> keeps the focus inside, Escape cancels.

import { button, el } from './dom.ts';

export type Choice<T> = { label: string; value: T; primary?: boolean };

/** Asks in a modal dialog; resolves to the chosen value, or null for Cancel (`cancel`, e.g. Close for a dialog that
 * only shows something) and Escape. */
export function ask<T>(
  title: string, body: (string | HTMLElement)[], choices: Choice<T>[], cancel = 'Cancel',
): Promise<T | null> {
  return new Promise((resolve) => {
    const dialog = el('dialog', { class: 'dialog', 'aria-labelledby': 'dialog-title' });
    const choose = (value: T | null) => (): void => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    dialog.addEventListener('cancel', choose(null));
    dialog.append(
      el('h2', { id: 'dialog-title' }, title),
      ...body.map((part) => (typeof part === 'string' ? el('p', { class: 'muted' }, part) : part)),
      el('div', { class: 'form-actions' },
        ...choices.map((choice) => button(choice.label, choose(choice.value), { class: choice.primary ? 'primary' : null })),
        button(cancel, choose(null), { class: null })),
    );
    document.body.append(dialog);
    dialog.showModal();
  });
}
