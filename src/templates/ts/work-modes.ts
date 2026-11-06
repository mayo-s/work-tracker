// The ways of working (SPEC 5.11): what a user tracks, and the choice of it in the setup and the settings.

import { api, type WorkMode } from './api.ts';
import { el } from './dom.ts';

/** Name and meaning of each way of working. */
export const WORK_MODES: [WorkMode, string, string][] = [
  ['developer', 'Developer', 'Tickets and activities; ticket work can be marked as coding.'],
  ['tickets', 'Tickets, no coding', 'Tickets and activities, without coding work.'],
  ['activities', 'Activities only', 'Activities such as meetings or travel, no tickets.'],
  ['times', 'Times only', 'Start, end and break of each day, no entries.'],
];

export function workModeLabel(mode: WorkMode): string {
  return WORK_MODES.find(([value]) => value === mode)?.[1] ?? mode;
}

/** Whether entries can be ticket entries (and services matter). */
export function hasTickets(mode: WorkMode): boolean {
  return mode === 'developer' || mode === 'tickets';
}

/** The way of working of the user; in the team view (a `member`) the pages stay as they were (TASKS.md 13.6). */
export async function ownWorkMode(member: string | null): Promise<WorkMode> {
  return member ? 'developer' : (await api.settings()).work_mode;
}

/** A part of the work report (month, year); "Ticket work" is all ticket work, in place of "Coding work" and "Other
 * ticket work". */
export type WorkPart = 'coding' | 'other_work' | 'ticket_work' | 'activities';

/** The work of a period (month or year report) as lists: by service, by activity type. */
type Work = { coding: unknown[]; other_work: unknown[]; activities: unknown[] };

/** The parts of the work report: those of the way of working and those with data in the period (SPEC 5.11). Without
 * coding, ticket work is one part, unless coding work was recorded in the period. */
export function workParts(mode: WorkMode, work: Work): WorkPart[] {
  const parts: WorkPart[] = [];
  if (mode === 'developer' || work.coding.length) {
    parts.push('coding', 'other_work');
  } else if (hasTickets(mode) || work.other_work.length) {
    parts.push('ticket_work');
  }
  if (mode !== 'times' || work.activities.length) {
    parts.push('activities');
  }
  return parts;
}

/** Radio buttons of the ways of working; `onChoose` gets the chosen one and its name. */
export function workModeChoice(selected: WorkMode, onChoose: (mode: WorkMode, label: string) => void): HTMLFieldSetElement {
  const choices = WORK_MODES.map(([value, label, meaning]) => {
    const radio = el('input', { type: 'radio', name: 'work_mode', value, checked: value === selected });
    radio.addEventListener('change', () => onChoose(value, label));
    return el('label', {}, radio, el('span', {}, label, el('span', { class: 'muted' }, ` – ${meaning}`)));
  });
  return el('fieldset', { class: 'work-modes' }, el('legend', {}, 'Way of working'), ...choices);
}
