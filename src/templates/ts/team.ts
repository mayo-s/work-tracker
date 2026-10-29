// Team page (/team): a team's members, open invitations and services, for its team admins and the admin.

import { api, type InvitationView, type MemberView, type Service, type TeamPageView } from './api.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { el } from './dom.ts';
import { button, renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { field, submit } from './forms.ts';

const ROLE_LABELS: Record<MemberView['role'], string> = { admin: 'Admin', team_admin: 'Team admin', user: 'Member' };

/** The team to show: `?team=` (the admin opens any team from the admin page), otherwise the user's own. */
export function teamId(search: string, own: number | null): number | null {
  const requested = Number(new URLSearchParams(search).get('team'));
  return Number.isInteger(requested) && requested > 0 ? requested : own;
}

function membersSection(team: TeamPageView, me: string | undefined, page: Page): HTMLElement {
  const row = (member: MemberView): HTMLTableRowElement => el('tr', {},
    el('td', {}, el('strong', {}, member.username), member.user_id === me ? el('span', { class: 'muted' }, ' (you)') : ''),
    el('td', {}, [member.first_name, member.last_name].filter(Boolean).join(' ')),
    el('td', {}, member.email),
    el('td', {}, ROLE_LABELS[member.role]),
    el('td', {}, formatDate(member.joined_on)),
    el('td', { class: 'row-actions' }, member.user_id === me ? '' : button('Remove', () => {
      if (window.confirm(`Remove ${member.username} from ${team.name}? The team services their tickets use become `
        + 'personal services of theirs.')) {
        api.removeMember(team.id, member.user_id).then(() => page.reload(`Removed ${member.username}`), page.fail);
      }
    })));
  const header = el('tr', {}, ...['Username', 'Name', 'E-mail address', 'Role', 'Member since']
    .map((label) => el('th', {}, label)), el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')));
  return el('section', { class: 'review-section', id: 'members' },
    el('h2', {}, 'Members'),
    el('p', { class: 'muted' }, 'Accounts only: nobody\'s days or entries are shown here. Members leave in their settings.'),
    team.members.length
      ? el('table', { class: 'review-table list-table' }, el('thead', {}, header), el('tbody', {}, ...team.members.map(row)))
      : el('p', {}, 'No members yet.'));
}

function inviteForm(team: TeamPageView, page: Page): HTMLFormElement {
  const email = el('input', { id: 'invite-email', name: 'email', type: 'email', autocomplete: 'off' });
  const form = el('form', { class: 'balance-form invite-form', novalidate: true },
    field('invite', 'email', 'E-mail address', email, 'The exact address of the user (upper and lower case do not matter).'),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, 'Invite')));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    let message = '';
    void submit(form, 'invite', ['email'],
      () => api.invite(team.id, email.value.trim()).then((sent) => (message = sent.message)), () => page.reload(message));
  });
  return form;
}

function invitationsSection(team: TeamPageView, page: Page): HTMLElement {
  const row = (invitation: InvitationView): HTMLTableRowElement => el('tr', {},
    el('td', {}, invitation.email),
    el('td', {}, formatTimestamp(invitation.invited_at)),
    el('td', { class: 'row-actions' }, button('Withdraw', () => {
      api.withdrawInvitation(team.id, invitation.id)
        .then(() => page.reload(`Withdrew the invitation to ${invitation.email}`), page.fail);
    })));
  return el('section', { class: 'review-section', id: 'invitations' },
    el('h2', {}, 'Invitations'),
    el('p', { class: 'muted' },
      'The invited user accepts or declines in their settings; accepting leaves their current team.'),
    team.invitations.length
      ? el('table', { class: 'review-table list-table' },
        el('thead', {}, el('tr', {}, el('th', {}, 'E-mail address'), el('th', {}, 'Invited'),
          el('th', {}, el('span', { class: 'visually-hidden' }, 'Actions')))),
        el('tbody', {}, ...team.invitations.map(row)))
      : el('p', {}, 'No open invitations.'),
    inviteForm(team, page));
}

function servicesTable(teamId: number, services: Service[]): EditableTable {
  return {
    id: 'team-services',
    title: 'Team services',
    hint: 'Members choose these in their entries, next to their personal services. Deleting one leaves the members\' '
      + 'tickets with it without service.',
    noun: 'team service',
    fields: [
      { name: 'short_name', label: 'Short name', maxLength: 30, required: true },
      { name: 'name', label: 'Full name', maxLength: 100, required: false },
    ],
    items: services.map((service) => ({
      id: service.id!, label: service.short_name, values: { short_name: service.short_name, name: service.name ?? '' },
    })),
    save: (id, values) => {
      const service = { short_name: values['short_name'] ?? '', name: values['name'] ?? '' };
      return id === null ? api.addTeamService(teamId, service) : api.updateTeamService(teamId, id, service);
    },
    remove: (id) => api.deleteTeamService(teamId, id),
    deleteQuestion: (item) => `Delete ${item.label}? Members' tickets with it lose their service and show up in their review.`,
  };
}

export async function renderTeamPage(doc: Document): Promise<void> {
  const status = await api.authStatus();
  const id = teamId(doc.location.search, status.team?.id ?? null);
  const root = doc.querySelector<HTMLElement>('#team');
  if (id === null) {
    root?.replaceChildren(el('div', { class: 'card' }, 'You are not in a team.'));
    return;
  }
  await renderEditablePage(doc, 'team', 'team-status', async (page) => {
    const [team, services] = await Promise.all([api.team(id), api.teamServices(id)]);
    doc.querySelector('#team-title')!.textContent = `Team ${team.name}`;
    doc.title = `Team ${team.name} · Work Tracker`;
    return [membersSection(team, status.user?.id, page), invitationsSection(team, page),
      tableSection(servicesTable(id, services), page)];
  });
}
