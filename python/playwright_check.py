"""Load a page from Singapore with Playwright (Python) and check what a local visitor sees.

    pip install -r requirements.txt && playwright install chromium
    HTTPS_PROXY=http://user:pass@host:port python playwright_check.py
"""
import sys

from playwright.sync_api import sync_playwright

from geo_common import SG_LAT, SG_LON, config, evaluate, proxy_settings, report


def main():
    cfg = config()
    server, user, pw = proxy_settings()
    proxy = None
    if server:
        proxy = {"server": server}
        if user:
            proxy.update(username=user, password=pw or "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg["headless"], proxy=proxy)
        # Match the browser to the IP. A Singapore IP with a US timezone and locale is a
        # mismatch that sites notice, and it isn't what a real local visitor looks like.
        context = browser.new_context(
            locale=cfg["locale"],
            timezone_id=cfg["timezone"],
            geolocation={"latitude": SG_LAT, "longitude": SG_LON},
            permissions=["geolocation"],
        )
        page = context.new_page()
        response = page.goto(cfg["target_url"], wait_until="load", timeout=cfg["timeout_ms"])
        page.wait_for_timeout(cfg["settle_ms"])  # let consent banners and currency scripts run

        text = page.inner_text("body")
        consent = page.locator(cfg["consent_selector"]).count() > 0 if cfg["consent_selector"] else None
        tz = page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
        if cfg["screenshot"]:
            page.screenshot(path=cfg["screenshot"], full_page=True)
        summary = evaluate(cfg, page.url, response.status if response else None, text, consent, tz)
        browser.close()
    return report(summary)


if __name__ == "__main__":
    sys.exit(main())
