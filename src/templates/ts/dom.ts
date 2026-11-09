// Small DOM builder: text is always inserted as text (never as HTML), so data cannot inject markup.

type Child = Node | string | null | undefined | false;
type Attributes = Record<string, string | number | boolean | null | undefined>;

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attributes: Attributes = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === true) {
      element.setAttribute(name, '');
    } else if (value !== false && value !== null && value !== undefined) {
      element.setAttribute(name, String(value));
    }
  }
  for (const child of children) {
    if (child) {
      element.append(child);
    }
  }
  return element;
}

/** A button that calls `onClick`; small unless `attributes` give another class. */
export function button(label: string, onClick: () => void, attributes: Attributes = {}): HTMLButtonElement {
  const element = el('button', { type: 'button', class: 'button-small', ...attributes }, label);
  element.addEventListener('click', onClick);
  return element;
}

/** Phones (SPEC 5.5a): the width below which pages show their mobile view, as in main.css. */
export const PHONE = '(max-width: 40rem)';

/** Each body cell gets the text of its column's header as `data-label`, shown before it on phones; none for a header
 * that only screen readers see (e.g. "Actions"), one with a control (select all) or a cell spanning columns. */
export function labelCells(table: HTMLTableElement): void {
  const labels = [...(table.tHead?.rows[0]?.cells ?? [])].flatMap((cell) => Array<string>(cell.colSpan)
    .fill(cell.querySelector('.visually-hidden, input') ? '' : (cell.textContent ?? '').trim()));
  for (const row of [...table.tBodies].flatMap((body) => [...body.rows])) {
    let column = 0;
    for (const cell of row.cells) {
      const label = cell.colSpan === 1 ? labels[column] : '';
      if (label) {
        cell.dataset.label = label;
      } else {
        delete cell.dataset.label;
      }
      column += cell.colSpan;
    }
  }
}

/** A table in an area of its own that scrolls sideways when the table is wider than the screen, instead of the page
 * (WCAG 1.4.10 Reflow); while it scrolls, the area takes the focus, so it scrolls with the keyboard too. On phones a
 * list table's rows become blocks instead (`stacks`, SPEC 5.5a), its cells labelled again whenever its rows change;
 * not the week (cards there) and not the tables of label and value. */
export function scrolling(table: HTMLTableElement): HTMLElement {
  if (!table.matches('.week-table, .card-table')) {
    table.classList.add('stacks');
    labelCells(table);
    new MutationObserver(() => labelCells(table)).observe(table, { childList: true, subtree: true });
  }
  const area = el('div', { class: 'table-scroll' }, table);
  const observer = new ResizeObserver(() => {
    if (area.scrollWidth > area.clientWidth) {
      area.setAttribute('tabindex', '0');
    } else {
      area.removeAttribute('tabindex');
    }
  });
  observer.observe(area);
  observer.observe(table);
  return area;
}

/** Calls `handler` when Escape is pressed within `element`, e.g. to cancel an inline form. */
export function onEscape(element: HTMLElement, handler: () => void): void {
  element.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      handler();
    }
  });
}
