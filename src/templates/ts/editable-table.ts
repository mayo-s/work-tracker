// An editable table of records (add, edit inline, delete) and the page frame around such tables, with a status line.

import { ApiError } from './api.ts';
import { el, onEscape } from './dom.ts';
import { WEEKDAY_NAMES } from './labels.ts';

/**
 * A field of a record, e.g. the short name of a service; `fixed` fields can only be entered for a new record.
 * `weekdays` fields hold weekday names separated by commas (`Mon,Tue`), entered with one checkbox per day;
 * `select` fields offer `options` (value and label); `checkbox` fields hold `true` or `false`.
 */
export type Field = {
  name: string;
  label: string;
  required: boolean;
  maxLength?: number;
  type?: 'text' | 'number' | 'date' | 'weekdays' | 'select' | 'checkbox';
  options?: [string, string][];
  defaultValue?: string;
  format?: (value: string) => string;
  min?: number;
  max?: number;
  step?: number;
  numeric?: boolean;
  fixed?: boolean;
  placeholder?: string;
};

/** A record as text values by field name; `label` names it in messages, `usage` fills the optional usage column. */
export type Item = { id: number; label: string; values: Record<string, string>; usage?: string };

/** One editable table: its records and how to save and delete them. */
export type EditableTable = {
  id: string;
  title: string;
  hint: string;
  noun: string;
  fields: Field[];
  usageLabel?: string;
  items: Item[];
  save: (id: number | null, values: Record<string, string>) => Promise<unknown>;
  remove: (id: number) => Promise<unknown>;
  deleteQuestion: (item: Item) => string;
};

export type Page = { reload: (message: string) => void; fail: (error: unknown) => void };

export function button(label: string, onClick: () => void, className = 'button-small'): HTMLButtonElement {
  const element = el('button', { type: 'button', class: className }, label);
  element.addEventListener('click', onClick);
  return element;
}

/** The element to enter a field's value, and how to read the value back as text. */
type Control = { name: string; element: HTMLElement; read: () => string };

function controlLabel(item: Item, field: Field): string {
  return `${field.label} of ${item.label}`;
}

/**
 * Edit rows sit under the column headers, so their controls are named by `aria-label`;
 * the form for a new record shows a label above each control.
 */
function named(item: Item | null, field: Field, control: HTMLElement): HTMLElement {
  if (item) {
    control.setAttribute('aria-label', controlLabel(item, field));
    return control;
  }
  return el('label', { class: 'list-field' }, el('span', { class: 'field-label' }, field.label), control);
}

function inputControl(item: Item | null, field: Field): Control {
  const input = el('input', {
    name: field.name,
    type: field.type ?? 'text',
    value: item?.values[field.name] ?? field.defaultValue ?? '',
    placeholder: field.placeholder ?? (item ? field.label : null),
    maxlength: field.maxLength,
    min: field.min,
    max: field.max,
    step: field.step,
    required: field.required,
    autocomplete: 'off',
  });
  return { name: field.name, element: named(item, field, input), read: () => input.value.trim() };
}

function weekdaysControl(item: Item | null, field: Field): Control {
  const selected = new Set((item?.values[field.name] ?? field.defaultValue ?? '').split(','));
  const boxes = WEEKDAY_NAMES.map((day) => el('input', { type: 'checkbox', value: day, checked: selected.has(day) }));
  const picker = el('fieldset', { class: 'weekday-picker' },
    el('legend', { class: 'visually-hidden' }, item ? controlLabel(item, field) : field.label),
    ...boxes.map((box, index) => el('label', {}, box, WEEKDAY_NAMES[index])));
  const label = el('span', { class: 'field-label', 'aria-hidden': 'true' }, field.label);  // the legend names it
  const element = item ? picker : el('div', { class: 'list-field' }, label, picker);
  return { name: field.name, element, read: () => boxes.filter((box) => box.checked).map((box) => box.value).join(',') };
}

function selectControl(item: Item | null, field: Field): Control {
  const value = item?.values[field.name] ?? field.defaultValue ?? '';
  const select = el('select', { name: field.name },
    ...(field.options ?? []).map(([option, label]) => el('option', { value: option, selected: option === value }, label)));
  return { name: field.name, element: named(item, field, select), read: () => select.value };
}

function checkboxControl(item: Item | null, field: Field): Control {
  const box = el('input', { type: 'checkbox', checked: (item?.values[field.name] ?? field.defaultValue) === 'true',
    'aria-label': item ? controlLabel(item, field) : null });
  const element = el('label', { class: 'checkbox-field' }, box, field.label);
  return { name: field.name, element, read: () => String(box.checked) };
}

const CONTROLS = { weekdays: weekdaysControl, select: selectControl, checkbox: checkboxControl };

function controls(table: EditableTable, item: Item | null): Control[] {
  return table.fields.filter((field) => !(item && field.fixed))
    .map((field) => (CONTROLS[field.type as keyof typeof CONTROLS] ?? inputControl)(item, field));
}

function values(fields: Control[]): Record<string, string> {
  return Object.fromEntries(fields.map((control) => [control.name, control.read()]));
}

/** Saves the form's values (a new record if `item` is null), then reloads the page with a message. */
function itemForm(table: EditableTable, item: Item | null, page: Page, ...buttons: HTMLElement[]): HTMLFormElement {
  const fields = controls(table, item);
  const fixed = item
    ? table.fields.filter((field) => field.fixed).map((field) => el('strong', {}, item.values[field.name])) : [];
  const form = el('form', { class: 'list-form' }, ...fixed, ...fields.map((control) => control.element), ...buttons);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const entered = values(fields);
    const name = item?.label ?? entered[table.fields[0]!.name];
    const message = `${item ? 'Saved' : 'Added'} ${table.noun} ${name}`;
    table.save(item?.id ?? null, entered).then(() => page.reload(message), page.fail);
  });
  return form;
}

function editRow(table: EditableTable, item: Item, page: Page, row: HTMLTableRowElement, opener: HTMLElement): void {
  const original = [...row.childNodes];
  const columns = table.fields.length + (table.usageLabel ? 2 : 1);
  const cancel = (): void => {
    row.replaceChildren(...original);
    opener.focus();
  };
  const form = itemForm(table, item, page,
    el('button', { type: 'submit', class: 'button-small primary' }, 'Save'), button('Cancel', cancel));
  onEscape(form, cancel);
  row.replaceChildren(el('td', { colspan: columns }, form));
  queueMicrotask(() => form.querySelector<HTMLElement>('input, select')?.focus());
}

function cell(field: Field, value: string | undefined, first: boolean): HTMLElement {
  const text = value && field.format ? field.format(value) : value;
  const content = !text ? el('span', { class: 'muted' }, '—') : first ? el('strong', {}, text) : text;
  return el('td', { class: field.numeric ? 'num' : null }, content);
}

function itemRow(table: EditableTable, item: Item, page: Page): HTMLTableRowElement {
  const row = el('tr', {});
  const edit: HTMLButtonElement = button('Edit', () => editRow(table, item, page, row, edit));
  row.append(
    ...table.fields.map((field, index) => cell(field, item.values[field.name], index === 0)),
    table.usageLabel ? el('td', { class: 'num' }, item.usage ?? '') : '',
    el('td', { class: 'row-actions' },
      edit,
      button('Delete', () => {
        if (window.confirm(table.deleteQuestion(item))) {
          table.remove(item.id).then(() => page.reload(`Deleted ${table.noun} ${item.label}`), page.fail);
        }
      })),
  );
  return row;
}

export function tableSection(table: EditableTable, page: Page): HTMLElement {
  const header = el('tr', {},
    ...table.fields.map((field) => el('th', { class: field.numeric ? 'num' : null }, field.label)),
    table.usageLabel ? el('th', { class: 'num' }, table.usageLabel) : '',
    el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')));
  return el('section', { class: 'review-section', id: table.id },
    el('h2', {}, table.title),
    el('p', { class: 'muted' }, table.hint),
    table.items.length
      ? el('table', { class: 'review-table list-table' }, el('thead', {}, header),
        el('tbody', {}, ...table.items.map((item) => itemRow(table, item, page))))
      : el('p', {}, `No ${table.noun}s yet.`),
    itemForm(table, null, page, el('button', { type: 'submit', class: 'primary' }, `Add ${table.noun}`)),
  );
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'The action failed.';
}

/** Renders the sections built by `build` into `#rootId`, reloading them after each change with a message in `#statusId`. */
export async function renderEditablePage(
  doc: Document, rootId: string, statusId: string, build: (page: Page) => Promise<HTMLElement[]>,
): Promise<void> {
  const root = doc.querySelector<HTMLElement>(`#${rootId}`);
  const status = doc.querySelector<HTMLElement>(`#${statusId}`);
  if (!root || !status) {
    return;
  }
  const show = (message: string, warning = false): void => {
    status.textContent = message;
    status.className = warning ? 'review-status field-error' : 'review-status value-positive';
    status.hidden = !message;
  };
  const load = async (message = ''): Promise<void> => {
    try {
      const page: Page = { reload: (text) => void load(text), fail: (error) => show(errorText(error), true) };
      root.replaceChildren(...await build(page));
      show(message);
    } catch (error) {
      root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' }, errorText(error)));
    }
  };
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  await load();
}
