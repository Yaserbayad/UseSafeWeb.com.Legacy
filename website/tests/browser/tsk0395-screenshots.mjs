import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const output = new URL('../../artifacts/tsk0395/', import.meta.url);
const cases = [
  { locale: 'en-GB', width: 390, height: 844, name: 'en-GB-mobile.png' },
  { locale: 'en-GB', width: 1440, height: 1000, name: 'en-GB-desktop.png' },
  { locale: 'ar', width: 390, height: 844, name: 'ar-mobile-rtl.png' },
];

await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });

try {
  for (const item of cases) {
    const context = await browser.newContext({ viewport: { width: item.width, height: item.height } });
    const page = await context.newPage();
    const response = await page.goto(`${base}/${item.locale}`, { waitUntil: 'networkidle' });
    if (!response || response.status() !== 200) {
      throw new Error(`screenshot target failed: ${item.locale} ${item.width}px status=${response?.status() ?? 'none'}`);
    }
    await page.screenshot({ path: new URL(item.name, output).pathname, fullPage: true });
    await context.close();
    console.log(`TSK0395_SCREENSHOT=${item.name}`);
  }
} finally {
  await browser.close();
}

console.log('TSK0395_SCREENSHOTS=PASS');
