// A modal question with buttons: a native <dialog> keeps the focus inside, Escape cancels.

import { el } from './dom.ts';

export type Choice<T> = { label: string; value: T; primary?: boolean };

/** Asks in a modal dialog; resolves to the chosen value, or null for Cancel and Escape. */
export function ask<T>(title: string, body: (string | HTMLElement)[], choices: Choice<T>[]): Promise<T | null> {
  return new Promise((resolve) => {
    const dialog = el('dialog', { class: 'dialog', 'aria-labelledby': 'dialog-title' });
    const choose = (value: T | null) => (): void => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    const button = (label: string, value: T | null, className = ''): HTMLButtonElement => {
      const element = el('button', { type: 'button', class: className }, label);
      element.addEventListener('click', choose(value));
      return element;
    };
    dialog.addEventListener('cancel', choose(null));
    dialog.append(
      el('h2', { id: 'dialog-title' }, title),
      ...body.map((part) => (typeof part === 'string' ? el('p', { class: 'muted' }, part) : part)),
      el('div', { class: 'form-actions' },
        ...choices.map((choice) => button(choice.label, choice.value, choice.primary ? 'primary' : '')),
        button('Cancel', null)),
    );
    document.body.append(dialog);
    dialog.showModal();
  });
}
