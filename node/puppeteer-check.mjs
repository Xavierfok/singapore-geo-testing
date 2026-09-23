// Load a page from Singapore with Puppeteer and check what a local visitor sees.
//
//   npm ci
//   HTTPS_PROXY=http://user:pass@host:port node puppeteer-check.mjs
import puppeteer from 'puppeteer';
import { SG_GEO, config, evaluate, proxySettings, report } from './common.mjs';

const cfg = config();
const proxy = proxySettings();

if (proxy?.username && proxy.server.startsWith('socks')) {
  console.error("error: Chrome can't authenticate to a SOCKS proxy. Use the HTTP port, or whitelist your IP.");
  process.exit(2);
}

const args = [`--lang=${cfg.locale}`];
if (proxy) args.push(`--proxy-server=${proxy.server}`);

const browser = await puppeteer.launch({ headless: cfg.headless, args });
try {
  const page = await browser.newPage();
  // Chrome takes the proxy address as a flag but the credentials only as an auth answer.
  if (proxy?.username) await page.authenticate({ username: proxy.username, password: proxy.password ?? '' });

  await page.emulateTimezone(cfg.timezone);
  await page.setExtraHTTPHeaders({ 'Accept-Language': `${cfg.locale},en;q=0.8` });
  const origin = new URL(cfg.targetUrl).origin;
  if (origin.startsWith('https:')) {
    // Browsers only expose geolocation to secure origins, so there's nothing to grant on http.
    await browser.defaultBrowserContext().overridePermissions(origin, ['geolocation']);
    await page.setGeolocation(SG_GEO);
  }

  const response = await page.goto(cfg.targetUrl, { waitUntil: 'load', timeout: cfg.timeoutMs });
  await new Promise((r) => setTimeout(r, cfg.settleMs)); // let consent banners and currency scripts run

  const summary = evaluate(cfg, {
    finalUrl: page.url(),
    status: response?.status(),
    text: await page.evaluate(() => document.body.innerText),
    consentPresent: cfg.consentSelector ? (await page.$(cfg.consentSelector)) !== null : null,
    browserTz: await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
  });
  if (cfg.screenshot) await page.screenshot({ path: cfg.screenshot, fullPage: true });
  process.exitCode = report(summary);
} finally {
  await browser.close();
}
