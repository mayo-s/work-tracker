// Component gallery (/components): index, color swatches and copyable HTML for every example.

/** The HTML of an example, without the indentation of the page source. */
export function snippet(html: string): string {
  const lines = html.replace(/^\n+|\s+$/g, '').split('\n');
  const indents = lines.filter((line) => line.trim()).map((line) => line.length - line.trimStart().length);
  const indent = Math.min(...indents, Infinity);
  return lines.map((line) => line.slice(Number.isFinite(indent) ? indent : 0)).join('\n');
}

/** The `--color-*` variables of the stylesheet, e.g. ['--color-text', '#36454f']. */
export function colorVariables(sheets: Iterable<CSSStyleSheet>, style: CSSStyleDeclaration): [string, string][] {
  const names = new Set<string>();
  for (const sheet of sheets) {
    for (const rule of Array.from(sheet.cssRules)) {
      if (rule instanceof CSSStyleRule && rule.selectorText === ':root') {
        Array.from(rule.style).filter((name) => name.startsWith('--color-')).forEach((name) => names.add(name));
      }
    }
  }
  return [...names].map((name) => [name, style.getPropertyValue(name).trim()]);
}

function renderIndex(index: HTMLElement, stories: HTMLElement[]): void {
  for (const story of stories) {
    const link = document.createElement('a');
    link.href = `#${story.id}`;
    link.textContent = story.querySelector('h2')?.textContent ?? story.id;
    const item = document.createElement('li');
    item.append(link);
    index.append(item);
  }
}

function renderSnippets(stories: HTMLElement[]): void {
  for (const example of stories.flatMap((story) => Array.from(story.querySelectorAll<HTMLElement>('.story-example')))) {
    const code = document.createElement('code');
    code.textContent = snippet(example.innerHTML);
    const block = document.createElement('pre');
    block.className = 'story-code';
    block.append(code);
    example.after(block);
  }
}

function renderSwatches(container: HTMLElement): void {
  for (const [name, value] of colorVariables(Array.from(document.styleSheets), getComputedStyle(document.documentElement))) {
    const swatch = document.createElement('div');
    swatch.className = 'swatch';
    swatch.innerHTML = '<span class="swatch-color"></span><code></code><span class="num muted"></span>';
    swatch.querySelector<HTMLElement>('.swatch-color')!.style.background = `var(${name})`;
    swatch.querySelector('code')!.textContent = name;
    swatch.querySelector('.muted')!.textContent = value;
    container.append(swatch);
  }
}

export function renderGallery(root: ParentNode): void {
  const stories = Array.from(root.querySelectorAll<HTMLElement>('.story'));
  const index = root.querySelector<HTMLElement>('#gallery-index');
  const swatches = root.querySelector<HTMLElement>('#swatches');
  if (index) {
    renderIndex(index, stories);
  }
  if (swatches) {
    renderSwatches(swatches);
  }
  renderSnippets(stories);
}
