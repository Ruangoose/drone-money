"""Cached HTTP for the sources (SEC EDGAR, USAspending, Kenneth French, Alpaca).

Every response is cached under data/cache/ keyed by method, URL and body, so a rerun reads the cache and a
clean clone downloads afresh. Set DVP_REFRESH=1 to ignore the cache.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"

# SEC asks automated clients to identify themselves with a contact address: set SEC_USER_AGENT to your name
# and email (for example "Jane Doe jane@example.com") before downloading from EDGAR.
SEC_UA = os.environ.get("SEC_USER_AGENT")

_last_call = {}


def _throttle(host, min_gap):
    gap = time.time() - _last_call.get(host, 0)
    if gap < min_gap:
        time.sleep(min_gap - gap)
    _last_call[host] = time.time()


def _key(method, url, body):
    raw = method + " " + url + " " + (json.dumps(body, sort_keys=True) if body is not None else "")
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def fetch(url, method="GET", body=None, headers=None, binary=False, min_gap=0.0, retries=3, cache=True,
          timeout=120):
    """Return the response text (or bytes), from the cache when present."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (_key(method, url, body) + (".bin" if binary else ".txt"))
    if cache and path.exists() and os.environ.get("DVP_REFRESH") != "1":
        return path.read_bytes() if binary else path.read_text(encoding="utf-8")
    host = requests.utils.urlparse(url).netloc
    if "sec.gov" in host and not SEC_UA:
        raise RuntimeError("Set SEC_USER_AGENT to your name and email before downloading from SEC EDGAR")
    h = {"User-Agent": SEC_UA} if "sec.gov" in host else {"User-Agent": "drone-money research"}
    h.update(headers or {})
    for attempt in range(retries):
        _throttle(host, min_gap)
        try:
            if method == "POST":
                r = requests.post(url, json=body, headers=h, timeout=timeout)
            else:
                r = requests.get(url, headers=h, timeout=timeout)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        r.raise_for_status()
        if cache:
            if binary:
                path.write_bytes(r.content)
            else:
                path.write_text(r.text, encoding="utf-8")
        return r.content if binary else r.text
    raise RuntimeError(f"failed after {retries} tries: {method} {url}")


def get_json(url, **kw):
    return json.loads(fetch(url, **kw))


def post_json(url, body, **kw):
    return json.loads(fetch(url, method="POST", body=body, **kw))


def sec_json(url):
    # SEC's fair-access limit is 10 requests a second.
    return get_json(url, min_gap=0.12)


def sec_text(url):
    return fetch(url, min_gap=0.12)
