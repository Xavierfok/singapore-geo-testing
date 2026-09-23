// Shared config and checks for the Node recipes. Same environment variables as the Python ones.

export const DEFAULT_TARGET = 'https://www.cloudflare.com/cdn-cgi/trace';
export const DEFAULT_EXPECT = 'loc=SG';

// Singapore geolocation (Raffles Place) for browsers that ask for it.
export const SG_GEO = { latitude: 1.284, longitude: 103.851 };

/**
 * Proxy as { server, username, password }, or null when none is set.
 * SG_PROXY_* (exported by setup-singapore-proxy) wins over the usual *_PROXY variables.
 */
export function proxySettings(env = process.env) {
  if (env.SG_PROXY_SERVER) {
    return {
      server: env.SG_PROXY_SERVER,
      username: env.SG_PROXY_USERNAME || undefined,
      password: env.SG_PROXY_PASSWORD || undefined,
    };
  }
  for (const name of ['HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'HTTP_PROXY', 'http_proxy']) {
    let raw = env[name];
    if (!raw) continue;
    if (!raw.includes('://')) raw = `http://${raw}`;
    const u = new URL(raw);
    return {
      server: `${u.protocol}//${u.host}`,
      username: u.username ? decodeURIComponent(u.username) : undefined,
      password: u.password ? decodeURIComponent(u.password) : undefined,
    };
  }
  return null;
}

export function config(env = process.env) {
  const target = env.TARGET_URL || DEFAULT_TARGET;
  return {
    targetUrl: target,
    expectText: env.EXPECT_TEXT ?? (target === DEFAULT_TARGET ? DEFAULT_EXPECT : ''),
    forbidText: env.FORBID_TEXT || '',
    expectUrl: env.EXPECT_URL || '',
    consentSelector: env.CONSENT_SELECTOR || '',
    consentExpect: (env.CONSENT_EXPECT || 'absent').toLowerCase(),
    timezone: env.GEO_TIMEZONE || 'Asia/Singapore',
    locale: env.GEO_LOCALE || 'en-SG',
    screenshot: env.SCREENSHOT || '',
    headless: env.HEADLESS !== '0',
    timeoutMs: Number(env.TIMEOUT_MS || 45000),
    settleMs: Number(env.SETTLE_MS || 1500),
  };
}

function snippet(pattern, text) {
  const m = new RegExp(pattern).exec(text);
  return m ? m[0].slice(0, 80) : null;
}

/** Run the configured checks against what the browser saw. */
export function evaluate(cfg, { finalUrl, status, text, consentPresent, browserTz }) {
  const checks = [];
  const add = (check, ok, detail) => checks.push({ check, ok: Boolean(ok), detail });

  add('http_status', status != null && status < 400, `status ${status}`);
  if (cfg.expectUrl) add('final_url', new RegExp(cfg.expectUrl).test(finalUrl), `${finalUrl} vs /${cfg.expectUrl}/`);
  if (cfg.expectText) {
    const hit = snippet(cfg.expectText, text);
    add('expect_text', hit, hit ? `found '${hit}'` : `no match for /${cfg.expectText}/`);
  }
  if (cfg.forbidText) {
    const hit = snippet(cfg.forbidText, text);
    add('forbid_text', !hit, hit ? `found '${hit}'` : `no match for /${cfg.forbidText}/`);
  }
  if (cfg.consentSelector) {
    const want = cfg.consentExpect === 'present';
    add('consent_banner', consentPresent === want,
      `${cfg.consentSelector} ${consentPresent ? 'present' : 'absent'}, expected ${cfg.consentExpect}`);
  }
  add('browser_timezone', browserTz === cfg.timezone, `${browserTz}, expected ${cfg.timezone}`);
  return { target: cfg.targetUrl, final_url: finalUrl, ok: checks.every((c) => c.ok), checks };
}

export function report(summary) {
  console.log(JSON.stringify(summary, null, 2));
  return summary.ok ? 0 : 1;
}
