// The ways of working (SPEC 5.11): what a user tracks, and the choice of it in the setup and the settings.

import type { WorkMode } from './api.ts';
import { el } from './dom.ts';
import { t } from './i18n.ts';

/** Name and meaning of each way of working. */
export const WORK_MODES: [WorkMode, string, string][] = [
  ['tickets', t('Tickets and activities'),
    t('Work on tickets (e.g. Coding) with their service, and activities such as meetings.')],
  ['activities', t('Activities only'), t('Activities such as meetings or travel, no tickets.')],
  ['times', t('Times only'), t('Start, end and break of each day, no entries.')],
];

export function workModeLabel(mode: WorkMode): string {
  return WORK_MODES.find(([value]) => value === mode)?.[1] ?? mode;
}

/** Whether entries can be ticket entries (and services matter). */
export function hasTickets(mode: WorkMode): boolean {
  return mode === 'tickets';
}

/** Whether the month and year report show the work: always, but in "Times only" only when the period holds entries
 * (SPEC 5.11). */
export function showsWork(mode: WorkMode, recorded: boolean): boolean {
  return mode !== 'times' || recorded;
}

/** Radio buttons of the ways of working; `onChoose` gets the chosen one and its name. */
export function workModeChoice(selected: WorkMode, onChoose: (mode: WorkMode, label: string) => void): HTMLFieldSetElement {
  const choices = WORK_MODES.map(([value, label, meaning]) => {
    const radio = el('input', { type: 'radio', name: 'work_mode', value, checked: value === selected });
    radio.addEventListener('change', () => onChoose(value, label));
    return el('label', {}, radio, el('span', {}, label, el('span', { class: 'muted' }, ` – ${meaning}`)));
  });
  return el('fieldset', { class: 'work-modes' }, el('legend', {}, t('Way of working')), ...choices);
}
