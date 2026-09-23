"""Check where your traffic actually leaves from: IP, country, ASN and carrier. Stdlib only.

Run this before any browser recipe. If the exit isn't a Singapore mobile ASN, nothing the
browser shows you afterwards is what a Singapore mobile user sees.

    HTTPS_PROXY=http://user:pass@host:port python exit_check.py
"""
import json
import os
import sys
import urllib.request
from urllib.parse import urlsplit

from geo_common import die, proxy_url_with_auth

# Customer-visible mobile-data ASNs first, then each carrier's company/fixed-line ASNs.
# An IP on a fixed-line ASN is Singaporean but not mobile.
ASNS = {
    45143: ("singtel", True),   # SINGTELMOBILE-AS-AP
    7473: ("singtel", False),   # SINGTEL-AS-AP
    4773: ("m1", True),         # MOBILEONELTD-AS-AP
    17547: ("m1", False),       # M1NET-SG-AP
    9874: ("starhub", True),    # STARHUB-MOBILE
    4657: ("starhub", False),   # StarHub Internet
    55430: ("starhub", False),  # StarHub NGNBN
}


def main():
    info_url = os.environ.get("IP_INFO_URL", "https://ipinfo.io/json")
    expect_country = os.environ.get("EXPECT_COUNTRY", "SG")
    require_mobile = os.environ.get("REQUIRE_MOBILE", "1") != "0"

    proxy = proxy_url_with_auth()
    handlers = []
    if proxy:
        if urlsplit(proxy).scheme.startswith("socks"):
            die("urllib can't talk SOCKS. Point HTTPS_PROXY at the HTTP port of your proxy.")
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))  # no proxy set: measure the direct route
    opener = urllib.request.build_opener(*handlers)

    with opener.open(urllib.request.Request(info_url, headers={"Accept": "application/json"}), timeout=30) as r:
        data = json.load(r)

    org = data.get("org", "")
    asn = int(org.split()[0][2:]) if org.startswith("AS") and org.split()[0][2:].isdigit() else None
    carrier, mobile = ASNS.get(asn, ("unknown", False))
    checks = [
        {"check": "country", "ok": data.get("country") == expect_country,
         "detail": f"{data.get('country')}, expected {expect_country}"},
    ]
    if require_mobile:
        checks.append({"check": "mobile_asn", "ok": mobile,
                       "detail": f"{org or 'no ASN'} ({carrier}, {'mobile' if mobile else 'not a known SG mobile ASN'})"})
    summary = {"via_proxy": bool(proxy), "ip": data.get("ip"), "country": data.get("country"),
               "asn": f"AS{asn}" if asn else None, "org": org, "carrier": carrier, "mobile": mobile,
               "ok": all(c["ok"] for c in checks), "checks": checks}
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
