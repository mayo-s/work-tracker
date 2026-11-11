// The services and activity types to choose from in entries, as editable tables of the settings page.

import { api, type ActivityType, type Service, type ServiceChoice, type TicketView } from './api.ts';
import { el } from './dom.ts';
import type { EditableTable } from './editable-table.ts';
import { t, tn } from './i18n.ts';

/** Number of tickets per service id. */
export function ticketCounts(tickets: TicketView[]): Map<string, number> {
  const counts = new Map<string, number>();
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
    return t('Delete {name}? No ticket uses it.', { name: shortName });
  }
  return tn(tickets, 'Delete {name}? {count} ticket loses its service and shows up in the review.',
    'Delete {name}? {count} tickets lose their service and show up in the review.', { name: shortName });
}

/** Services to choose grouped as `Team <name>` (first) and `Personal`; one group without a name when there is no team. */
export function serviceGroups(choices: ServiceChoice[]): [string, ServiceChoice[]][] {
  const personal = t('Personal');
  const groups = new Map<string, ServiceChoice[]>();
  for (const choice of choices) {
    const group = choice.team ? t('Team {name}', { name: choice.team }) : personal;
    groups.set(group, [...groups.get(group) ?? [], choice]);
  }
  return groups.size === 1 && groups.has(personal) ? [['', choices]] : [...groups];
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
    title: t('Services'),
    hint: t('The service of a ticket applies to all its entries; the month report groups coding work by service. These are your personal services; the services of your team are managed by its team admins.'),
    texts: {
      added: (name) => t('Added service {name}', { name }), saved: (name) => t('Saved service {name}', { name }),
      deleted: (name) => t('Deleted service {name}', { name }), none: t('No services yet.'), add: t('Add service'),
    },
    fields: [
      { name: 'short_name', label: t('Short name'), maxLength: 30, required: true },
      { name: 'name', label: t('Full name'), maxLength: 100, required: false },
    ],
    usageLabel: t('Tickets'),
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
    title: t('Activity types'),
    hint: t('Every entry has one, e.g. Coding, Meeting or Travel; an entry of a type that requires a ticket needs one. A type used by entries cannot be deleted.'),
    texts: {
      added: (name) => t('Added activity type {name}', { name }), saved: (name) => t('Saved activity type {name}', { name }),
      deleted: (name) => t('Deleted activity type {name}', { name }), none: t('No activity types yet.'),
      add: t('Add activity type'),
    },
    fields: [
      { name: 'name', label: t('Name'), maxLength: 50, required: true },
      { name: 'ticket_required', label: t('Ticket required'), required: false, type: 'checkbox', defaultValue: 'false',
        format: (value) => (value === 'true' ? t('yes') : t('no')) },
    ],
    items: activityTypes.map((type) => ({
      id: type.id!, label: type.name, values: { name: type.name, ticket_required: String(type.ticket_required ?? false) },
    })),
    save: (id, input) => {
      const type = { name: input['name'] ?? '', ticket_required: input['ticket_required'] === 'true' };
      return id === null ? api.addActivityType(type) : api.updateActivityType(id, type);
    },
    remove: (id) => api.deleteActivityType(id),
    deleteQuestion: (item) => t('Delete {name}?', { name: item.label }),
  };
}
