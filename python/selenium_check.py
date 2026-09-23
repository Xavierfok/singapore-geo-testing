"""Load a page from Singapore with Selenium + Chrome and check what a local visitor sees.

Chrome can't take proxy credentials on the command line, so when the proxy needs a
username and password this starts a small local forwarder (geo_common.AuthForwarder)
that adds them, and points Chrome at that.

    pip install -r requirements.txt
    HTTPS_PROXY=http://user:pass@host:port python selenium_check.py
"""
import json
import sys
import time
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By

from geo_common import SG_LAT, SG_LON, AuthForwarder, config, die, evaluate, proxy_settings, report


def main():
    cfg = config()
    server, user, pw = proxy_settings()

    opts = webdriver.ChromeOptions()
    if cfg["headless"]:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--lang={cfg['locale']}")
    opts.add_experimental_option("prefs", {"intl.accept_languages": cfg["locale"]})
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    forwarder = None
    if server:
        p = urlsplit(server)
        if user and p.scheme.startswith("socks"):
            die("Chrome can't authenticate to a SOCKS proxy. Use the HTTP port, or whitelist your IP.")
        if user:
            forwarder = AuthForwarder(p.hostname, p.port, user, pw).start()
            opts.add_argument(f"--proxy-server=http://127.0.0.1:{forwarder.port}")
        else:
            opts.add_argument(f"--proxy-server={server}")

    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(cfg["timeout_ms"] / 1000)
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": cfg["timezone"]})
        driver.execute_cdp_cmd("Emulation.setGeolocationOverride",
                               {"latitude": SG_LAT, "longitude": SG_LON, "accuracy": 100})
        driver.get(cfg["target_url"])
        time.sleep(cfg["settle_ms"] / 1000)

        text = driver.find_element(By.TAG_NAME, "body").text
        consent = None
        if cfg["consent_selector"]:
            consent = len(driver.find_elements(By.CSS_SELECTOR, cfg["consent_selector"])) > 0
        tz = driver.execute_script("return Intl.DateTimeFormat().resolvedOptions().timeZone")
        if cfg["screenshot"]:
            driver.save_screenshot(cfg["screenshot"])
        summary = evaluate(cfg, driver.current_url, _main_document_status(driver), text, consent, tz)
    finally:
        driver.quit()
    return report(summary)


def _main_document_status(driver):
    """Selenium has no response object, so find the page's own response in Chrome's perf log.

    Iframes are Documents too, so match on the URL the tab ended up at.
    """
    status = None
    for entry in driver.get_log("performance"):
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") != "Network.responseReceived" or msg["params"].get("type") != "Document":
            continue
        if msg["params"]["response"]["url"] == driver.current_url:
            status = msg["params"]["response"]["status"]
    return status


if __name__ == "__main__":
    sys.exit(main())
