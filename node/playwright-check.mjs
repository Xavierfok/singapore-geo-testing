// Load a page from Singapore with Playwright (Node) and check what a local visitor sees.
//
//   npm ci && npx playwright install chromium
//   HTTPS_PROXY=http://user:pass@host:port node playwright-check.mjs
import { chromium } from 'playwright';
import { SG_GEO, config, evaluate, proxySettings, report } from './common.mjs';

const cfg = config();
const proxy = proxySettings();

const browser = await chromium.launch({ headless: cfg.headless, proxy: proxy ?? undefined });
// Match the browser to the IP: a Singapore IP with a US timezone and locale is a mismatch
// that sites notice, and it isn't what a real local visitor looks like.
const context = await browser.newContext({
  locale: cfg.locale,
  timezoneId: cfg.timezone,
  geolocation: SG_GEO,
  permissions: ['geolocation'],
});
const page = await context.newPage();
const response = await page.goto(cfg.targetUrl, { waitUntil: 'load', timeout: cfg.timeoutMs });
await page.waitForTimeout(cfg.settleMs); // let consent banners and currency scripts run

const summary = evaluate(cfg, {
  finalUrl: page.url(),
  status: response?.status(),
  text: await page.innerText('body'),
  consentPresent: cfg.consentSelector ? (await page.locator(cfg.consentSelector).count()) > 0 : null,
  browserTz: await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
});
if (cfg.screenshot) await page.screenshot({ path: cfg.screenshot, fullPage: true });
await browser.close();
process.exitCode = report(summary);
