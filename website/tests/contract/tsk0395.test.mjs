import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../..');
const read = (path) => readFileSync(resolve(root, path), 'utf8');
const json = (path) => JSON.parse(read(path));

const locales = ['en-GB', 'tr-TR', 'ar'];

for (const locale of locales) {
  test(`TSK-0395 ${locale} landing proposition is first-phone-led rather than DNS-led`, () => {
    const content = json(`src/content/${locale}.json`);
    assert.ok(content.home.kicker, 'missing localized first-phone category');
    assert.ok(content.home.title, 'missing localized first-phone proposition');
    assert.doesNotMatch(content.home.title, /dns/i, 'landing headline must not make DNS the product proposition');
    assert.doesNotMatch(content.home.summary, /^dns/i, 'landing summary must lead with the user outcome, not DNS');
    assert.ok(content.home.primaryLabel, 'missing primary setup CTA');
    assert.ok(content.home.secondaryLabel, 'missing secondary explanation CTA');
  });
}

test('TSK-0395 landing page renders canonical locale content and routes the primary CTA to accountless setup', () => {
  const page = read('src/app/[locale]/page.tsx');

  assert.match(page, /publicMetadata\(locale, '', content\.home\.title, content\.home\.summary\)/);
  assert.match(page, /LandingPage/);
  assert.match(page, /section=\{content\.home\}/);
  assert.match(page, /href: `\/\$\{locale\}\/start`/);
  assert.match(page, /href: `\/\$\{locale\}\/how-it-works`/);
  assert.match(page, /utilityLinks=\{\[/);
  assert.match(page, /content\.common\.nav\.limits/);
  assert.match(page, /content\.common\.nav\.privacy/);
  assert.match(page, /content\.common\.nav\.help/);
});

test('TSK-0395 landing exposes trust/support navigation in both global shell and landing composition', () => {
  const shell = read('src/components/site-shell.tsx');
  const landing = read('src/components/landing-page.tsx');

  assert.match(shell, /\['protection-and-limits', common\.nav\.limits\]/);
  assert.match(shell, /\['privacy', common\.nav\.privacy\]/);
  assert.match(shell, /\['help', common\.nav\.help\]/);
  assert.match(landing, /utilityLinks/);
  assert.match(landing, /className="sw-landing-trust"/);
});

test('TSK-0395 public landing is a materially distinct editorial composition rather than the generic content-page/card-grid shell', () => {
  const landing = read('src/components/landing-page.tsx');
  const css = read('src/app/globals.css');

  assert.match(landing, /<article className="sw-page sw-landing">/);
  assert.match(landing, /<h1 className="sw-title">/);
  assert.match(landing, /className="sw-landing-hero"/);
  assert.match(landing, /className="sw-landing-copy/);
  assert.match(landing, /className="sw-landing-visual/);
  assert.match(landing, /className="sw-landing-visual-mark"/);
  assert.match(landing, /className="sw-landing-trust"/);
  assert.match(landing, /className="sw-landing-feature-list"/);
  assert.match(landing, /className="sw-landing-feature"/);
  assert.doesNotMatch(landing, /sw-card-grid sw-landing-grid/);

  for (const selector of [
    '.sw-landing-hero',
    '.sw-landing-visual',
    '.sw-landing-trust',
    '.sw-landing-feature-list',
    '.sw-landing-feature',
  ]) {
    assert.ok(css.includes(selector), `missing landing style ${selector}`);
  }
  assert.match(css, /@media\s*\(min-width:\s*64rem\)/);
  assert.doesNotMatch(
    css,
    /#[0-9a-fA-F]{6}/,
    'landing must consume shared brand tokens rather than a parallel raw palette',
  );
});

test('TSK-0395 public header uses the canonical approved SafeWeb wordmark without forking its geometry', () => {
  const shell = read('src/components/site-shell.tsx');
  const publicWordmark = read('public/safeweb-wordmark-primary.svg');
  const canonicalWordmark = read('../brand/identity/TSK-0301/safeweb-wordmark-primary.svg');

  assert.match(shell, /src="\/safeweb-wordmark-primary\.svg"/);
  assert.equal(publicWordmark, canonicalWordmark);
});
