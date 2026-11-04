import { chromium } from 'playwright';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const FLYDIR = join(process.cwd(), 'marketing', 'flyers');
const files = readdirSync(FLYDIR).filter((f) => f.endsWith('.html')).sort();

const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
const page = await browser.newPage();
for (const f of files) {
  await page.goto(pathToFileURL(join(FLYDIR, f)).href, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  await page.emulateMedia({ media: 'print' });
  const out = join(FLYDIR, f.replace(/\.html$/, '.pdf'));
  await page.pdf({
    path: out,
    width: '8.5in',
    height: '11in',
    printBackground: true,
    margin: { top: '0', right: '0', bottom: '0', left: '0' },
  });
  console.log('pdf', out);
}
await browser.close();
