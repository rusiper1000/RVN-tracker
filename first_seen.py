#!/usr/bin/env python3
"""주소별 첫 거래일/마지막 거래일 조회: python first_seen.py [추가주소 ...]
기본 목록: 과거 1위, 현재 1위, RNqSvK…, RDN1XK…, RDQheY…, 그리고 data/hop2.json의 14개 분할 주소."""
import json, os, sys, time, urllib.request

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
NAMED = {
    "RRGYxRYGhvUuXBpvypLK9YdaXDk6Gs95LS": "과거 1위",
    "R9J3tqF6rXFQVUrrMxtkMBjgeobPmxLwXn": "현재 1위",
    "RNqSvKnzEzBgt9rUvaWCPBTyNtZRogEpo2": "RNqSvK(핫월렛 추정)",
    "RDN1XKwt24hziyfWQbqFdtrVN1CHuY32eT": "RDN1XK(현재 2위)",
    "RDQheYZszh52cGZgYuzSE5SbzwTeEzR4Jn": "RDQheY(현재 6위)",
}
def get(path):
    try:
        rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            return json.load(r)
    except Exception as e:
        print("  조회 실패:", e); return None
day = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t)) if t else "-"
def at(a, page):
    r = get(f"/address/{a}?details=txs&page={page}&pageSize=1")
    tx = (r or {}).get("transactions") or []
    return tx[0].get("blockTime", 0) if tx else 0

items = dict(NAMED)
hp = os.path.join(D, "hop2.json")
if os.path.exists(hp):
    for r in json.load(open(hp, encoding="utf-8"))["rows"]:
        items.setdefault(r["addr"], "14개 분할 주소")
for a in sys.argv[1:]:
    items.setdefault(a, "직접 입력")
for a, name in items.items():
    b = get(f"/address/{a}?details=basic")
    if not b:
        continue
    n = int(b.get("txs", 0))
    print(f"{day(at(a, n))} ~ {day(at(a, 1))}  거래 {n:,}건  잔고 {int(b['balance'])/1e8:,.0f}  {name}  {a[:12]}…", flush=True)
    time.sleep(0.4)
