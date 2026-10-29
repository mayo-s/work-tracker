// The services and activity types to choose from in entries, as editable tables of the settings page.

import { api, type ActivityType, type Service, type ServiceChoice, type TicketView } from './api.ts';
import { el } from './dom.ts';
import type { EditableTable } from './editable-table.ts';

/** Number of tickets per service id. */
export function ticketCounts(tickets: TicketView[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const ticket of tickets) {
    if (ticket.service_id !== null) {
      counts.set(ticket.service_id, (counts.get(ticket.service_id) ?? 0) + 1);
    }
  }
  return counts;
}

/** `Delete MSB? 12 tickets lose their service and show up in the review.` */
export function deleteServiceQuestion(shortName: string, tickets: number): string {
  if (!tickets) {
    return `Delete ${shortName}? No ticket uses it.`;
  }
  return tickets === 1
    ? `Delete ${shortName}? 1 ticket loses its service and shows up in the review.`
    : `Delete ${shortName}? ${tickets} tickets lose their service and show up in the review.`;
}

/** Services to choose grouped as `Team <name>` (first) and `Personal`; one group without a name when there is no team. */
export function serviceGroups(choices: ServiceChoice[]): [string, ServiceChoice[]][] {
  const groups = new Map<string, ServiceChoice[]>();
  for (const choice of choices) {
    const group = choice.team ? `Team ${choice.team}` : 'Personal';
    groups.set(group, [...groups.get(group) ?? [], choice]);
  }
  return groups.size === 1 && groups.has('Personal') ? [['', choices]] : [...groups];
}

/** The options of a service select, in groups while the user is in a team; `label` gives each option's text. */
export function serviceOptions(choices: ServiceChoice[], label: (choice: ServiceChoice) => string): HTMLElement[] {
  const options = (group: ServiceChoice[]): HTMLOptionElement[] =>
    group.map((choice) => el('option', { value: choice.id ?? '' }, label(choice)));
  return serviceGroups(choices).flatMap(([name, group]) => (name ? [el('optgroup', { label: name }, ...options(group))]
    : options(group)));
}

export function servicesTable(services: Service[], tickets: TicketView[]): EditableTable {
  const counts = ticketCounts(tickets);
  return {
    id: 'services',
    title: 'Services',
    hint: 'The service of a ticket applies to all its entries; the month report groups coding work by service. These are '
      + 'your personal services; the services of your team are managed by its team admins.',
    noun: 'service',
    fields: [
      { name: 'short_name', label: 'Short name', maxLength: 30, required: true },
      { name: 'name', label: 'Full name', maxLength: 100, required: false },
    ],
    usageLabel: 'Tickets',
    items: services.map((service) => ({
      id: service.id!, label: service.short_name, values: { short_name: service.short_name, name: service.name ?? '' },
      usage: String(counts.get(service.id!) ?? 0),
    })),
    save: (id, input) => {
      const service = { short_name: input['short_name'] ?? '', name: input['name'] ?? '' };
      return id === null ? api.addService(service) : api.updateService(id, service);
    },
    remove: (id) => api.deleteService(id),
    deleteQuestion: (item) => deleteServiceQuestion(item.label, counts.get(item.id) ?? 0),
  };
}

export function activityTypesTable(activityTypes: ActivityType[]): EditableTable {
  return {
    id: 'activity-types',
    title: 'Activity types',
    hint: 'For entries without a ticket, e.g. meetings or travel. A type used by entries cannot be deleted.',
    noun: 'activity type',
    fields: [{ name: 'name', label: 'Name', maxLength: 50, required: true }],
    items: activityTypes.map((type) => ({ id: type.id!, label: type.name, values: { name: type.name } })),
    save: (id, input) => {
      const type = { name: input['name'] ?? '' };
      return id === null ? api.addActivityType(type) : api.updateActivityType(id, type);
    },
    remove: (id) => api.deleteActivityType(id),
    deleteQuestion: (item) => `Delete ${item.label}?`,
  };
}
