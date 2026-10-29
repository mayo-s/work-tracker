// Dashboard (start page /): key figures, the overtime balance over time, days off coming up and this year's figures.

import { api, ApiError, type DashboardView } from './api.ts';
import { formatDate, formatDay, formatMonth, type IsoDate } from './dates.ts';
import { el } from './dom.ts';
import { DAY_TYPE_LABELS } from './labels.ts';
import { valueClass } from './week.ts';
import { formatDays } from './year.ts';

type Point = DashboardView['balance_series']['month'][number];
type Range = keyof DashboardView['balance_series'];
type ComingUp = DashboardView['coming_up'][number];

const RANGES: [Range, string][] = [['month', 'Month'], ['year', 'Year'], ['last_12_months', '12 months'], ['all', 'All']];
const SVG = 'http://www.w3.org/2000/svg';
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MARGIN = { top: 16, right: 72, bottom: 28, left: 56 };
const HEIGHT = 240;

/** Axis ticks in whole hours (as minutes) covering min, max and zero: at most about five, at round steps. */
export function hourTicks(minMinutes: number, maxMinutes: number): number[] {
  const low = Math.min(0, minMinutes) / 60;
  const high = Math.max(0, maxMinutes) / 60;
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find((candidate) => (high - low) / candidate <= 5) ?? 1000;
  const ticks: number[] = [];
  for (let tick = Math.floor(low / step) * step; tick <= Math.ceil(high / step) * step; tick += step) {
    ticks.push(tick * 60);
  }
  return ticks;
}

/** `Wed 28.10.2026` for days, `October 2026` for month ends. */
export function pointLabel(point: Point, range: Range): string {
  const weekday = WEEKDAYS[new Date(`${point.date}T12:00:00`).getDay()]!;
  return range === 'month'
    ? `${formatDay(point.date, weekday)}${point.date.slice(0, 4)}` : formatMonth(point.date.slice(0, 7));
}

/** The indexes of the x-axis labels: at most `count`, evenly spread, always including the last point. */
export function labelIndexes(length: number, count: number): number[] {
  if (length <= count) {
    return [...Array(length).keys()];
  }
  const step = Math.ceil((length - 1) / (count - 1));
  const indexes = [...Array(length).keys()].filter((index) => index % step === 0 && length - 1 - index >= step / 2);
  return [...indexes, length - 1];
}

/** `Thu 05.11. – Mon 09.11. · PTO · 3 days`, or `Fri 25.12. · Christmas Day` for a holiday. */
export function describeComingUp(item: ComingUp): string {
  const day = (date: IsoDate): string => formatDay(date, WEEKDAYS[new Date(`${date}T12:00:00`).getDay()]!);
  const dates = item.start === item.end ? day(item.start) : `${day(item.start)} – ${day(item.end)}`;
  const label = item.holiday ?? DAY_TYPE_LABELS[item.day_type];
  return [dates, label, item.days > 1 ? `${item.days} days` : ''].filter(Boolean).join(' · ');
}

function tile(label: string, value: string, detail: string, href: string, valueClassName = ''): HTMLElement {
  return el('a', { class: 'tile', href },
    el('span', { class: 'tile-label' }, label),
    el('span', { class: `tile-value ${valueClassName}`.trim() }, value),
    el('span', { class: 'tile-detail' }, detail));
}

function keyFigures(data: DashboardView): HTMLElement {
  const pto = data.pto;
  const week = data.this_week;
  const change = data.balance_change_this_year;
  return el('div', { class: 'tiles' },
    tile('Overtime balance', data.balance, `${change.startsWith('-') ? change : `+${change}`} this year`, '/year',
      valueClass(data.balance)),
    pto ? tile(`PTO left ${data.today.slice(0, 4)}`, `${formatDays(pto.remaining)} days`, `${formatDays(pto.planned)} planned`,
      '/year', pto.remaining < 0 ? 'value-negative' : '')
      : tile('PTO', '—', 'No PTO days entered', '/settings#pto-years'),
    tile('This week', `${week.worked} of ${data.week_target}`, `Overtime so far ${week.overtime}`, `/week?week=${data.week}`),
    tile('To review', String(data.review_open), data.review_open ? 'open items' : 'nothing to review', '/review',
      data.review_open ? 'value-negative' : ''));
}

function svg<K extends keyof SVGElementTagNameMap>(
  tag: K, attributes: Record<string, string | number>,
): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  return element;
}

type Geometry = { x: (index: number) => number; y: (minutes: number) => number; width: number; ticks: number[] };

function geometry(points: Point[], width: number): Geometry {
  const values = points.map((point) => point.minutes);
  const ticks = hourTicks(Math.min(...values), Math.max(...values));
  const low = ticks[0]!;
  const high = ticks.at(-1)!;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  return {
    width,
    ticks,
    x: (index) => MARGIN.left + (points.length > 1 ? (index * plotWidth) / (points.length - 1) : plotWidth / 2),
    y: (minutes) => MARGIN.top + ((high - minutes) * plotHeight) / (high - low || 1),
  };
}

/** Grid lines and hour labels, the zero line, and the x-axis labels. */
function axes(points: Point[], range: Range, g: Geometry): SVGGElement {
  const group = svg('g', { class: 'chart-axes' });
  for (const tick of g.ticks) {
    group.append(svg('line', { x1: MARGIN.left, x2: g.width - MARGIN.right, y1: g.y(tick), y2: g.y(tick),
      class: tick === 0 ? 'chart-zero' : 'chart-grid' }));
    const label = svg('text', { x: MARGIN.left - 8, y: g.y(tick) + 4, 'text-anchor': 'end', class: 'chart-text' });
    label.textContent = `${tick / 60} h`;
    group.append(label);
  }
  for (const index of labelIndexes(points.length, range === 'month' ? 6 : 7)) {
    const label = svg('text', { x: g.x(index), y: HEIGHT - 8, 'text-anchor': 'middle', class: 'chart-text' });
    const date = points[index]!.date;
    label.textContent = range === 'month'
      ? `${Number(date.slice(8))}.` : formatMonth(date.slice(0, 7)).replace(/^(\w{3})\w*/, '$1');  // Oct 2026
    group.append(label);
  }
  return group;
}

/** The line and its area wash, in the accent above zero and the warning color below (two clipped copies). */
function balanceMarks(points: Point[], g: Geometry, id: string): SVGGElement {
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${g.x(index)},${g.y(point.minutes)}`).join(' ');
  const area = `${line} L${g.x(points.length - 1)},${g.y(0)} L${g.x(0)},${g.y(0)} Z`;
  const group = svg('g', {});
  const defs = svg('defs', {});
  for (const [name, top, bottom] of [['above', 0, g.y(0)], ['below', g.y(0), HEIGHT]] as const) {
    const clip = svg('clipPath', { id: `${id}-${name}` });
    clip.append(svg('rect', { x: 0, y: top, width: g.width, height: Math.max(bottom - top, 0) }));
    defs.append(clip);
    const part = svg('g', { 'clip-path': `url(#${id}-${name})`, class: `chart-${name}` });
    part.append(svg('path', { d: area, class: 'chart-area' }), svg('path', { d: line, class: 'chart-line' }));
    group.append(part);
  }
  group.prepend(defs);
  return group;
}

function endMark(points: Point[], g: Geometry): SVGGElement {
  const last = points.at(-1)!;
  const group = svg('g', { class: last.minutes < 0 ? 'chart-below' : 'chart-above' });
  group.append(svg('circle', { cx: g.x(points.length - 1), cy: g.y(last.minutes), r: 4, class: 'chart-dot' }));
  const label = svg('text', { x: g.x(points.length - 1) + 10, y: g.y(last.minutes) + 4, class: 'chart-text chart-end-label' });
  label.textContent = last.balance;
  group.append(label);
  return group;
}

/** Crosshair and tooltip on hover, and the same with the arrow keys once the chart has focus. */
function hoverLayer(chart: HTMLElement, plot: SVGSVGElement, points: Point[], range: Range, g: Geometry): void {
  const crosshair = svg('line', {
    y1: MARGIN.top, y2: HEIGHT - MARGIN.bottom, class: 'chart-crosshair', visibility: 'hidden',
  });
  const dot = svg('circle', { r: 4, class: 'chart-dot', visibility: 'hidden' });
  plot.append(crosshair, dot);
  const tip = el('div', { class: 'chart-tooltip', hidden: true });
  chart.append(tip);
  let current = points.length - 1;
  const show = (index: number): void => {
    current = Math.max(0, Math.min(points.length - 1, index));
    const point = points[current]!;
    const x = g.x(current);
    crosshair.setAttribute('x1', String(x));
    crosshair.setAttribute('x2', String(x));
    dot.setAttribute('cx', String(x));
    dot.setAttribute('cy', String(g.y(point.minutes)));
    dot.setAttribute('class', `chart-dot ${point.minutes < 0 ? 'chart-below' : 'chart-above'}`);
    crosshair.setAttribute('visibility', 'visible');
    dot.setAttribute('visibility', 'visible');
    tip.replaceChildren(el('strong', { class: `num ${valueClass(point.balance)}` }, point.balance),
      el('span', { class: 'muted' }, pointLabel(point, range)));
    tip.hidden = false;
    tip.style.left = `${Math.min(x, g.width - 140)}px`;
  };
  const hide = (): void => {
    crosshair.setAttribute('visibility', 'hidden');
    dot.setAttribute('visibility', 'hidden');
    tip.hidden = true;
  };
  plot.addEventListener('pointermove', (event) => {
    const box = plot.getBoundingClientRect();
    const x = ((event.clientX - box.left) * g.width) / box.width;
    show(Math.round(((x - MARGIN.left) / (g.width - MARGIN.left - MARGIN.right)) * (points.length - 1)));
  });
  plot.addEventListener('pointerleave', hide);
  plot.addEventListener('focus', () => show(current));
  plot.addEventListener('blur', hide);
  plot.addEventListener('keydown', (event) => {
    const moves: Record<string, number> = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 0, End: points.length - 1 };
    if (event.key in moves) {
      event.preventDefault();
      show(moves[event.key]!);
    }
  });
}

function balanceTable(points: Point[], range: Range): HTMLElement {
  return el('details', { class: 'chart-table' },
    el('summary', {}, 'Show as table'),
    el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}, range === 'month' ? 'Day' : 'Month'), el('th', { class: 'num' }, 'Balance'))),
      el('tbody', {}, ...points.map((point) => el('tr', {}, el('td', {}, pointLabel(point, range)),
        el('td', { class: `num ${valueClass(point.balance)}` }, point.balance))))));
}

function balanceChart(points: Point[], range: Range, width: number): HTMLElement {
  const chart = el('div', { class: 'chart' });
  if (!points.length) {
    chart.append(el('p', { class: 'muted' }, 'No balance yet: counting starts on the first day.'));
    return chart;
  }
  const g = geometry(points, width);
  const plot = svg('svg', { viewBox: `0 0 ${width} ${HEIGHT}`, width, height: HEIGHT, tabindex: 0, class: 'chart-plot',
    'aria-label': 'Overtime balance; arrow keys read the values, or show them as a table below' });
  plot.append(axes(points, range, g), balanceMarks(points, g, `balance-${range}`), endMark(points, g));
  chart.append(plot);
  hoverLayer(chart, plot, points, range, g);
  chart.append(balanceTable(points, range));
  return chart;
}

function balanceSection(data: DashboardView): HTMLElement {
  let range: Range = 'year';
  let width = 0;
  const holder = el('div', {});
  const draw = (): void => {
    holder.replaceChildren(balanceChart(data.balance_series[range], range, Math.max(width, 320)));
  };
  const switcher = el('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Period of the chart' },
    ...RANGES.map(([value, label]) => {
      const input = el('input', {
        type: 'radio', name: 'balance-range', value, id: `range-${value}`, checked: value === range,
      });
      input.addEventListener('change', () => {
        range = value;
        draw();
      });
      return el('label', { for: `range-${value}` }, input, label);
    }));
  new ResizeObserver(() => {
    if (holder.clientWidth !== width) {  // redraw on a new width only, not on the height the chart itself sets
      width = holder.clientWidth;
      draw();
    }
  }).observe(holder);
  return el('section', { class: 'dashboard-section' },
    el('div', { class: 'dashboard-section-header' }, el('h2', {}, 'Overtime balance'), switcher),
    el('div', { class: 'card' }, holder));
}

function comingUpSection(items: ComingUp[]): HTMLElement {
  return el('section', { class: 'card' },
    el('h2', {}, 'Coming up'),
    el('p', { class: 'muted' }, 'Public holidays and planned days off in the next 60 days.'),
    items.length
      ? el('ul', { class: 'coming-up' }, ...items.map((item) => el('li', {}, describeComingUp(item))))
      : el('p', {}, 'Nothing planned.'));
}

function yearSection(figures: DashboardView['this_year']): HTMLElement {
  const row = (label: string, value: string): HTMLElement =>
    el('tr', {}, el('td', {}, label), el('td', { class: 'num' }, value));
  const top = figures.top_services.map((service) => `${service.service ?? 'No service'} ${service.duration}`).join(', ');
  return el('section', { class: 'card' },
    el('h2', {}, `This year ${figures.year}`),
    el('table', { class: 'card-table' }, el('tbody', {},
      row('Days worked', String(figures.days_worked)),
      row('Average per day worked', figures.average_per_day_worked),
      row('Sick days', formatDays(figures.sick_days)),
      row('Overtime off', `${figures.overtime_off_days} days`),
      row('Coding hours', figures.coding),
      row('Top services', top || '—'))));
}

export async function renderDashboardPage(doc: Document): Promise<void> {
  const root = doc.querySelector<HTMLElement>('#dashboard');
  if (!root) {
    return;
  }
  root.replaceChildren(el('p', { class: 'muted' }, 'Loading…'));
  try {
    const data = await api.dashboard();
    doc.querySelector('#dashboard-today')!.textContent = `Today, ${formatDate(data.today)} · counted up to today`;
    root.replaceChildren(keyFigures(data), balanceSection(data),
      el('div', { class: 'dashboard-columns' }, comingUpSection(data.coming_up), yearSection(data.this_year)));
  } catch (error) {
    root.replaceChildren(el('div', { class: 'card is-warning', role: 'alert' },
      error instanceof ApiError ? error.message : 'The dashboard could not be loaded.'));
  }
}

