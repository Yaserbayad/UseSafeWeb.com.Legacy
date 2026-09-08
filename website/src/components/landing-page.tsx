import Link from 'next/link';

type Card = { title: string; body: string };
type Action = { href: string; label: string; secondary?: boolean };

type LandingSection = {
  kicker: string;
  title: string;
  summary: string;
  cards?: Card[];
  noteTitle?: string;
  noteBody?: string;
};

function actionClassName(action: Action) {
  return action.secondary ? 'sw-button sw-button--secondary' : 'sw-button';
}

export function LandingPage({
  section,
  actions = [],
}: {
  section: LandingSection;
  actions?: Action[];
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
                  className={actionClassName(action)}
                  href={action.href}
                >
                  {action.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        {section.noteTitle && section.noteBody && (
          <aside className="sw-callout sw-landing-proof">
            <strong>{section.noteTitle}</strong>
            <p>{section.noteBody}</p>
          </aside>
        )}
      </section>

      {section.cards && (
        <div className="sw-card-grid sw-landing-grid">
          {section.cards.map((card) => (
            <section className="sw-card" key={card.title}>
              <h2>{card.title}</h2>
              <p>{card.body}</p>
            </section>
          ))}
        </div>
      )}
    </article>
  );
}
