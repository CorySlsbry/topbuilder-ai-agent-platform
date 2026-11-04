import { chromium } from 'playwright';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const FLYDIR = join(process.cwd(), 'marketing', 'flyers');
const only = process.argv[2];
const files = readdirSync(FLYDIR)
  .filter((f) => f.endsWith('.html') && (!only || f.includes(only)))
  .sort();

const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
const page = await browser.newPage({
  viewport: { width: 816, height: 1056 },
  deviceScaleFactor: 2,
});
for (const f of files) {
  await page.goto(pathToFileURL(join(FLYDIR, f)).href, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  const out = join(FLYDIR, f.replace(/\.html$/, '.png'));
  await page.screenshot({ path: out });
  console.log('rendered', out);
}
await browser.close();
