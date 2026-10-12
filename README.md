# singapore-geo-testing

[![CI](https://github.com/Xavierfok/singapore-geo-testing/actions/workflows/ci.yml/badge.svg)](https://github.com/Xavierfok/singapore-geo-testing/actions/workflows/ci.yml)

Small, runnable recipes for checking what a visitor in Singapore actually sees on your site:
the geo-redirect they land on, the currency on the price, whether the EU cookie banner shows up,
and whether the browser looks like it's in Singapore at all.

Each recipe loads one page through a proxy, runs a few checks and prints a JSON result. It exits
non-zero when a check fails, so it drops straight into CI.

| Recipe | File |
| --- | --- |
| Playwright (Python) | [`python/playwright_check.py`](python/playwright_check.py) |
| Selenium + Chrome (Python) | [`python/selenium_check.py`](python/selenium_check.py) |
| Playwright (Node) | [`node/playwright-check.mjs`](node/playwright-check.mjs) |
| Puppeteer (Node) | [`node/puppeteer-check.mjs`](node/puppeteer-check.mjs) |
| Exit IP, country, ASN and carrier (stdlib only) | [`python/exit_check.py`](python/exit_check.py) |

All five read the same environment variables, so you can switch framework without touching your
CI config.

## Quick start

With no `TARGET_URL`, a recipe loads Cloudflare's trace page and checks it reports `loc=SG`.
That's a quick way to confirm the proxy works end to end.

```bash
export HTTPS_PROXY=http://user:pass@host:port

# Python
cd python
pip install -r requirements.txt && python -m playwright install chromium
python exit_check.py          # where does traffic leave from?
python playwright_check.py    # does the browser see Singapore?

# Node
cd node
npm ci && npx playwright install chromium
node playwright-check.mjs
node puppeteer-check.mjs
```

Then point it at your own page:

```bash
TARGET_URL=https://shop.example.com/ \
EXPECT_URL='/sg(/|$)' \
EXPECT_TEXT='S\$ ?[0-9]' \
FORBID_TEXT='US\$|€' \
CONSENT_SELECTOR='#onetrust-banner-sdk' \
python playwright_check.py
```

```json
{
  "target": "https://shop.example.com/",
  "final_url": "https://shop.example.com/sg/",
  "ok": true,
  "checks": [
    { "check": "http_status", "ok": true, "detail": "status 200" },
    { "check": "final_url", "ok": true, "detail": "https://shop.example.com/sg/ vs /sg(/|$)/" },
    { "check": "expect_text", "ok": true, "detail": "found 'S$ 129'" },
    { "check": "forbid_text", "ok": true, "detail": "no match for /US\\$|€/" },
    { "check": "consent_banner", "ok": true, "detail": "#onetrust-banner-sdk absent, expected absent" },
    { "check": "browser_timezone", "ok": true, "detail": "Asia/Singapore, expected Asia/Singapore" }
  ]
}
```

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `SG_PROXY_SERVER`, `SG_PROXY_USERNAME`, `SG_PROXY_PASSWORD` | | Proxy as separate parts. [setup-singapore-proxy](https://github.com/Xavierfok/setup-singapore-proxy) exports these. They win over the next row. |
| `HTTPS_PROXY` / `ALL_PROXY` / `HTTP_PROXY` | | Proxy as one URL, `http://user:pass@host:port`. |
| `TARGET_URL` | Cloudflare trace | Page to load. |
| `EXPECT_URL` | | Regex the final URL (after redirects) must match. |
| `EXPECT_TEXT` | `loc=SG` on the default target | Regex the visible page text must match. |
| `FORBID_TEXT` | | Regex the visible page text must not match. |
| `CONSENT_SELECTOR` | | CSS selector for a cookie/consent banner. |
| `CONSENT_EXPECT` | `absent` | `absent` or `present`. |
| `GEO_TIMEZONE` | `Asia/Singapore` | Browser timezone. |
| `GEO_LOCALE` | `en-SG` | Browser locale and `Accept-Language`. |
| `SCREENSHOT` | | Save a full-page screenshot to this path. |
| `SETTLE_MS` | `1500` | Wait after load, so consent and currency scripts can run. |
| `TIMEOUT_MS` | `45000` | Page-load timeout. |
| `HEADLESS` | `1` | `0` to watch the browser. |
| `IP_INFO_URL` | `https://ipinfo.io/json` | `exit_check.py` only: IP lookup returning ipinfo-style JSON. |
| `REQUIRE_MOBILE` | `1` | `exit_check.py` only: fail unless the ASN is a Singapore mobile network. |

## Why the browser settings matter

A Singapore IP is only half of it. If the browser still reports `America/Los_Angeles` and `en-US`,
you're testing a visitor who doesn't exist, and some sites treat that mismatch differently from a
real local visitor. Every recipe sets the timezone to `Asia/Singapore`, the locale to `en-SG` and
(on https pages) a Singapore geolocation, and the `browser_timezone` check confirms it took.

`exit_check.py` is the other half. It tells you whether the exit IP is on a Singapore **mobile**
network or just a Singapore IP. Mobile ASNs it knows: Singtel AS45143, M1 AS4773, StarHub AS138345
(and StarHub's older AS9874, which no longer announces any prefixes).
Home fibre and datacenter IPs are Singaporean but not mobile, and it says so.

## In CI

[`examples/geo-check.yml`](examples/geo-check.yml) is a nightly workflow you can copy. It uses
[`Xavierfok/setup-singapore-proxy@v1`](https://github.com/Xavierfok/setup-singapore-proxy) to route the job
through a Singapore mobile IP (failing early if the exit isn't Singtel or M1), then runs the Playwright
recipe against your storefront and uploads a screenshot.

This repo's own CI runs every recipe against [`fixture/fake_proxy.py`](fixture/fake_proxy.py), an
authenticating proxy that serves a fake storefront on `http://shop.test/`. `.test` has no DNS, so a
pass proves the browser really went through the proxy with the right credentials. It also checks that
an EU page and a wrong password both fail. No secrets or third-party sites needed.

## Notes and limits

- **Selenium and proxy passwords.** Chrome has no command-line flag for proxy credentials. The
  Selenium recipe starts a small local forwarder that adds them (`AuthForwarder` in
  [`geo_common.py`](python/geo_common.py)). Playwright and Puppeteer handle it natively.
- **SOCKS with a password doesn't work in Chrome** in any framework. Use the proxy's HTTP port, or
  IP whitelisting.
- **Puppeteer on Ubuntu 24.04 runners** fails with "No usable sandbox!" because AppArmor blocks
  unprivileged user namespaces. Add `echo 0 | sudo tee /proc/sys/kernel/apparmor_restrict_unprivileged_userns`
  before it runs (this repo's CI does). Playwright's Chromium isn't affected.
- **Google results aren't included.** Google's terms don't allow automated queries, so there's no
  recipe that scrapes a results page.
- **App Store region follows the Apple ID, not the IP.** The web preview at `apps.apple.com` doesn't
  switch storefront by IP, so a proxy can't test it. Google Play listings do vary by IP. Point
  `TARGET_URL` at your own listing and check the currency with `EXPECT_TEXT`.
- **Test your own sites**, or sites whose terms allow it. The recipes load one page per run and are
  meant for checking your own geo logic, not for crawling.

## Getting a Singapore mobile IP

The recipes work with any HTTP proxy. The worked examples use
[Singapore Mobile Proxy](https://singaporemobileproxy.com/?utm_source=github&utm_medium=repo), which
the author runs: real Singapore mobile IPs on Singtel or M1, with a rotation link for a fresh IP.
There's a free 24-hour trial (10 GB) at
[singaporemobileproxy.com/client/mcp](https://singaporemobileproxy.com/client/mcp?utm_source=github&utm_medium=repo),
then $4/day or $13/week.

## License

[MIT](LICENSE)
