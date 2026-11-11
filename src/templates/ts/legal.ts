// The texts the scripts add to imprint and privacy policy, in the language of the page's content (its `lang`): German,
// the binding text, or a translation (SPEC 5.16). Not in the catalogs: these pages are translated as a whole.

type LegalTexts = {
  heading: string; contact: string; email: string; contactForm: string; imprint: string;
  imprintMissing: string; imprintFailed: string; controllerMissing: string; controllerFailed: string;
};

const TEXTS: Record<string, LegalTexts> = {
  de: {
    heading: 'Angaben gemäß § 5 DDG', contact: 'Kontakt', email: 'E-Mail', contactForm: 'Kontaktformular',
    imprint: 'Impressum', imprintMissing: 'Das Impressum ist noch nicht eingerichtet.',
    imprintFailed: 'Das Impressum konnte nicht geladen werden.',
    controllerMissing: 'Der Verantwortliche ist noch nicht eingerichtet (siehe Impressum).',
    controllerFailed: 'Die Angaben zum Verantwortlichen konnten nicht geladen werden.',
  },
  en: {
    heading: 'Information pursuant to Section 5 DDG', contact: 'Contact', email: 'E-mail', contactForm: 'Contact form',
    imprint: 'Imprint', imprintMissing: 'The imprint is not set up yet.', imprintFailed: 'The imprint could not be loaded.',
    controllerMissing: 'The controller is not set up yet (see the imprint).',
    controllerFailed: 'The details of the controller could not be loaded.',
  },
  es: {
    heading: 'Información conforme al art. 5 DDG', contact: 'Contacto', email: 'Correo electrónico',
    contactForm: 'Formulario de contacto', imprint: 'Aviso legal', imprintMissing: 'El aviso legal aún no está configurado.',
    imprintFailed: 'No se pudo cargar el aviso legal.',
    controllerMissing: 'El responsable aún no está configurado (consulta el aviso legal).',
    controllerFailed: 'No se pudieron cargar los datos del responsable.',
  },
};

/** The texts for the content around `element`, German if its language has none. */
export function legalTexts(element: Element): LegalTexts {
  return TEXTS[element.closest('[lang]')?.getAttribute('lang') ?? 'de'] ?? TEXTS.de!;
}
