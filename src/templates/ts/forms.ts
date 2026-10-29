// Shared form helpers: fields with hint and error, validation errors from the API, saving state.

import { ApiError } from './api.ts';
import { el } from './dom.ts';

export type FieldErrors = { fields: Record<string, string>; general: string[] };

/** Validation messages without pydantic's "Value error, " prefix. */
export function cleanMessage(message: string): string {
  return message.replace(/^(Value error, )+/, '');
}

/** Validation errors of a 422 response, by field; errors not about one of the fields are general. */
export function fieldErrors(details: unknown, fields: readonly string[]): FieldErrors {
  const result: FieldErrors = { fields: {}, general: [] };
  for (const item of Array.isArray(details) ? details : []) {
    const field = item?.loc?.[0];
    const message = cleanMessage(String(item?.msg ?? ''));
    if (fields.includes(field)) {
      result.fields[field] = message;
    } else if (message) {
      result.general.push(message);
    }
  }
  return result;
}

/** A labelled field; its control has the id `${prefix}-${name}`, its error `${prefix}-${name}-error`. */
export function field(prefix: string, name: string, label: string, control: HTMLElement, hint?: string): HTMLElement {
  return el('div', { class: `field field-${name.replaceAll('_', '-')}` },
    el('label', { for: `${prefix}-${name}` }, label),
    control,
    hint ? el('p', { class: 'field-hint muted' }, hint) : null,
    el('p', { class: 'field-error', id: `${prefix}-${name}-error`, hidden: true }),
  );
}

export function showErrors(form: HTMLFormElement, prefix: string, fields: readonly string[], details: unknown, fallback: string): void {
  const errors = fieldErrors(details, fields);
  for (const name of fields) {
    const message = errors.fields[name];
    const error = form.querySelector<HTMLElement>(`#${prefix}-${name}-error`);
    if (error) {
      error.textContent = message ?? '';
      error.hidden = !message;
    }
    form.querySelector(`#${prefix}-${name}`)?.toggleAttribute('aria-invalid', Boolean(message));
  }
  const general = form.querySelector<HTMLElement>('.form-error')!;
  general.textContent = errors.general.join(' ') || (Object.keys(errors.fields).length ? '' : fallback);
  general.hidden = !general.textContent;
}

/** Runs a save or delete with disabled buttons; shows the errors in the form if it fails. */
export async function submit(
  form: HTMLFormElement, prefix: string, fields: readonly string[], action: () => Promise<unknown>, onDone: () => void,
): Promise<void> {
  form.querySelectorAll('button').forEach((button) => (button.disabled = true));
  try {
    await action();
    onDone();
  } catch (error) {
    const fallback = error instanceof ApiError ? error.message : 'Could not be saved.';
    showErrors(form, prefix, fields, error instanceof ApiError ? error.details : null, fallback);
    form.querySelectorAll('button').forEach((button) => (button.disabled = false));
  }
}

/** Form-level error line and the Save / Cancel / Delete buttons. */
export function formFooter(deleteLabel: string | null): HTMLElement[] {
  return [
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' },
      el('button', { type: 'submit', class: 'primary' }, 'Save'),
      el('button', { type: 'button', 'data-action': 'cancel' }, 'Cancel'),
      deleteLabel ? el('button', { type: 'button', class: 'button-danger', 'data-action': 'delete' }, deleteLabel) : null),
  ];
}
