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
