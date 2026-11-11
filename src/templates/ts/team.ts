// Team page (/team): a team's members, open invitations and services, for its team admins and the admin.

import { api, type InvitationView, type MemberView, type Service, type TeamPageView } from './api.ts';
import { formatDate, formatTimestamp } from './dates.ts';
import { button, el, scrolling } from './dom.ts';
import { renderEditablePage, tableSection, type EditableTable, type Page } from './editable-table.ts';
import { t } from './i18n.ts';
import { field, submit } from './forms.ts';

const ROLE_LABELS: Record<MemberView['team_role'], string> = { team_admin: t('Team admin'), member: t('Member') };

/** The team to show: `?team=` (the admin opens any team from the admin page), otherwise the user's own. */
export function teamId(search: string, own: string | null): string | null {
  return new URLSearchParams(search).get('team') || own;
}

function membersSection(team: TeamPageView, me: string | undefined, page: Page): HTMLElement {
  const row = (member: MemberView): HTMLTableRowElement => el('tr', {},
    el('td', {}, el('strong', {}, member.username), member.user_id === me ? el('span', { class: 'muted' }, ` ${t('(you)')}`) : ''),
    el('td', {}, [member.first_name, member.last_name].filter(Boolean).join(' ')),
    el('td', {}, member.email),
    el('td', {}, ROLE_LABELS[member.team_role]),
    el('td', {}, formatDate(member.joined_on)),
    el('td', { class: 'row-actions' }, member.user_id === me ? '' : button(t('Remove'), () => {
      const names = { user: member.username, team: team.name };
      if (window.confirm(t('Remove {user} from {team}? The team services their tickets use become personal services of theirs.',
        names))) {
        api.removeMember(team.id, member.user_id).then(() => page.reload(t('Removed {user}', names)), page.fail);
      }
    })));
  const header = el('tr', {}, ...[t('Username'), t('Name'), t('E-mail address'), t('Role'), t('Member since')]
    .map((label) => el('th', {}, label)), el('th', {}, el('span', { class: 'visually-hidden' }, t('Actions'))));
  return el('section', { class: 'review-section', id: 'members' },
    el('h2', {}, t('Members')),
    el('p', { class: 'muted' }, t('Accounts only: nobody\'s days or entries are shown here. Members leave in their settings.')),
    team.members.length
      ? scrolling(el('table', { class: 'review-table list-table' }, el('thead', {}, header), el('tbody', {}, ...team.members.map(row))))
      : el('p', {}, t('No members yet.')));
}

function inviteForm(team: TeamPageView, page: Page): HTMLFormElement {
  const email = el('input', { id: 'invite-email', name: 'email', type: 'email', autocomplete: 'off' });
  const form = el('form', { class: 'balance-form invite-form', novalidate: true },
    field('invite', 'email', t('E-mail address'), email, t('The exact address of the user (upper and lower case do not matter).')),
    el('p', { class: 'form-error field-error', role: 'alert', hidden: true }),
    el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'primary' }, t('Invite'))));
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
    el('td', { class: 'row-actions' }, button(t('Withdraw'), () => {
      api.withdrawInvitation(team.id, invitation.id)
        .then(() => page.reload(t('Withdrew the invitation to {email}', { email: invitation.email })), page.fail);
    })));
  return el('section', { class: 'review-section', id: 'invitations' },
    el('h2', {}, t('Invitations')),
    el('p', { class: 'muted' }, t('The invited user accepts or declines in their settings; accepting leaves their current team.')),
    team.invitations.length
      ? scrolling(el('table', { class: 'review-table list-table' },
        el('thead', {}, el('tr', {}, el('th', {}, t('E-mail address')), el('th', {}, t('Invited')),
          el('th', {}, el('span', { class: 'visually-hidden' }, t('Actions'))))),
        el('tbody', {}, ...team.invitations.map(row))))
      : el('p', {}, t('No open invitations.')),
    inviteForm(team, page));
}

function servicesTable(teamId: string, services: Service[]): EditableTable {
  return {
    id: 'team-services',
    title: t('Team services'),
    hint: t('Members choose these in their entries, next to their personal services. Deleting one leaves the members\' tickets with it without service.'),
    texts: {
      added: (name) => t('Added team service {name}', { name }), saved: (name) => t('Saved team service {name}', { name }),
      deleted: (name) => t('Deleted team service {name}', { name }), none: t('No team services yet.'),
      add: t('Add team service'),
    },
    fields: [
      { name: 'short_name', label: t('Short name'), maxLength: 30, required: true },
      { name: 'name', label: t('Full name'), maxLength: 100, required: false },
    ],
    items: services.map((service) => ({
      id: service.id!, label: service.short_name, values: { short_name: service.short_name, name: service.name ?? '' },
    })),
    save: (id, values) => {
      const service = { short_name: values['short_name'] ?? '', name: values['name'] ?? '' };
      return id === null ? api.addTeamService(teamId, service) : api.updateTeamService(teamId, id, service);
    },
    remove: (id) => api.deleteTeamService(teamId, id),
    deleteQuestion: (item) => t("Delete {name}? Members' tickets with it lose their service and show up in their review.",
      { name: item.label }),
  };
}

export async function renderTeamPage(doc: Document): Promise<void> {
  const status = await api.authStatus();
  const id = teamId(doc.location.search, status.team?.id ?? null);
  const root = doc.querySelector<HTMLElement>('#team');
  if (id === null) {
    root?.replaceChildren(el('div', { class: 'card' }, t('You are not in a team.')));
    return;
  }
  await renderEditablePage(doc, 'team', 'team-status', async (page) => {
    const [team, services] = await Promise.all([api.team(id), api.teamServices(id)]);
    doc.querySelector('#team-title')!.textContent = t('Team {name}', { name: team.name });
    doc.title = `${t('Team {name}', { name: team.name })} · Work Tracker`;
    return [membersSection(team, status.user?.id, page), invitationsSection(team, page),
      tableSection(servicesTable(id, services), page)];
  });
}
