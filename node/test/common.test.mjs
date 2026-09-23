import { test } from 'node:test';
import assert from 'node:assert/strict';
import { config, evaluate, proxySettings, DEFAULT_TARGET } from '../common.mjs';

test('SG_PROXY_* wins over HTTPS_PROXY', () => {
  const p = proxySettings({ SG_PROXY_SERVER: 'http://sg.example:8000', SG_PROXY_USERNAME: 'a', SG_PROXY_PASSWORD: 'b', HTTPS_PROXY: 'http://x:y@other:1' });
  assert.deepEqual(p, { server: 'http://sg.example:8000', username: 'a', password: 'b' });
});

test('HTTPS_PROXY is split into server and decoded credentials', () => {
  const p = proxySettings({ HTTPS_PROXY: 'http://us%40er:p%3Ass@host.example:8123' });
  assert.deepEqual(p, { server: 'http://host.example:8123', username: 'us@er', password: 'p:ss' });
});

test('no proxy set returns null', () => {
  assert.equal(proxySettings({}), null);
});

test('default target expects loc=SG, custom target expects nothing by default', () => {
  assert.equal(config({}).targetUrl, DEFAULT_TARGET);
  assert.equal(config({}).expectText, 'loc=SG');
  assert.equal(config({ TARGET_URL: 'https://shop.example/' }).expectText, '');
});

test('evaluate passes and fails on the right checks', () => {
  const cfg = config({ TARGET_URL: 'http://shop.test/', EXPECT_URL: '/sg/$', EXPECT_TEXT: 'S\\$', FORBID_TEXT: '€', CONSENT_SELECTOR: '#consent' });
  const good = evaluate(cfg, { finalUrl: 'http://shop.test/sg/', status: 200, text: 'S$ 129.00', consentPresent: false, browserTz: 'Asia/Singapore' });
  assert.equal(good.ok, true);
  const bad = evaluate(cfg, { finalUrl: 'http://shop.test/eu/', status: 200, text: '129,00 €', consentPresent: true, browserTz: 'Europe/Berlin' });
  assert.deepEqual(bad.checks.filter((c) => !c.ok).map((c) => c.check),
    ['final_url', 'expect_text', 'forbid_text', 'consent_banner', 'browser_timezone']);
});

test('a 407 from the proxy fails http_status', () => {
  const r = evaluate(config({}), { finalUrl: DEFAULT_TARGET, status: 407, text: '', consentPresent: null, browserTz: 'Asia/Singapore' });
  assert.equal(r.checks[0].ok, false);
});
