import Link from 'next/link';

type Card = { title: string; body: string };
type Action = { href: string; label: string; secondary?: boolean };
type UtilityLink = { href: string; label: string };

type LandingSection = {
  kicker: string;
  title: string;
  summary: string;
  cards?: Card[];
  noteTitle?: string;
  noteBody?: string;
};

export function LandingPage({
  section,
  actions = [],
  utilityLinks = [],
}: {
  section: LandingSection;
  actions?: Action[];
  utilityLinks?: UtilityLink[];
}) {
  return (
    <article className="sw-page sw-landing">
      <section className="sw-landing-hero">
        <div className="sw-landing-copy sw-stack">
          <p className="sw-kicker">{section.kicker}</p>
          <h1 className="sw-title">{section.title}</h1>
          <p className="sw-lede">{section.summary}</p>
          {actions.length > 0 && (
            <div className="sw-actions">
              {actions.map((action) => (
                <Link
                  key={action.href}
                  className={action.secondary ? 'sw-button sw-button--secondary' : 'sw-button'}
                  href={action.href}
                >
                  {action.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        {section.noteTitle && section.noteBody && (
          <aside className="sw-landing-visual" aria-labelledby="landing-evidence-title">
            <div className="sw-landing-visual-mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div className="sw-landing-visual-copy">
              <strong id="landing-evidence-title">{section.noteTitle}</strong>
              <p>{section.noteBody}</p>
            </div>
          </aside>
        )}
      </section>

      {utilityLinks.length > 0 && (
        <div className="sw-landing-trust">
          {utilityLinks.map((link) => (
            <Link key={link.href} href={link.href}>
              {link.label}
            </Link>
          ))}
        </div>
      )}

      {section.cards && (
        <div className="sw-landing-feature-list">
          {section.cards.map((card) => (
            <section className="sw-landing-feature" key={card.title}>
              <h2>{card.title}</h2>
              <p>{card.body}</p>
            </section>
          ))}
        </div>
      )}
    </article>
  );
}
