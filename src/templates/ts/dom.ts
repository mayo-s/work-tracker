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

/** A table in an area of its own that scrolls sideways when the table is wider than the screen, instead of the page
 * (WCAG 1.4.10 Reflow); while it scrolls, the area takes the focus, so it scrolls with the keyboard too. */
export function scrolling(table: HTMLTableElement): HTMLElement {
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
