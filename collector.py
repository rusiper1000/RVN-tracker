#!/usr/bin/env python3
"""과거 1위 주소(SRC) -> 현재 1위 주소(DST) 이체 추적기.
Insight API 호환 익스플로러를 사용한다. 주소를 바꾸려면 RVN_API 환경변수만 바꾸면 된다."""
import json, os, sys, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://ravencoin.network/api").rstrip("/")
SRC = "RRGYxRYGhvUuXBpvypLK9YdaXDk6Gs95LS"   # 과거 1위 (업비트 추정)
DST = "R9J3tqF6rXFQVUrrMxtkMBjgeobPmxLwXn"   # 현재 1위
OBSERVED = 5527986869.06                     # 스크린샷상 DST 증가분(RVN)
MAX_PAGES = int(os.environ.get("MAX_PAGES", "300"))
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def get(path):
    for i in range(4):
        try:
            rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
            with urllib.request.urlopen(rq, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            print("재시도:", path, e, file=sys.stderr); time.sleep(2 * (i + 1))
    sys.exit("API 호출 실패: " + path)

def load(name, default):
    p = os.path.join(D, name)
    return json.load(open(p)) if os.path.exists(p) else default

def save(name, obj):
    json.dump(obj, open(os.path.join(D, name), "w"), ensure_ascii=False)

# 1) 거래 수집 (최신순, 이미 본 페이지가 나오면 중단)
cache = load("txs_cache.json", {})
for page in range(MAX_PAGES):
    res = get(f"/txs/?address={SRC}&pageNum={page}")
    txs = res.get("txs", [])
    new = 0
    for tx in txs:
        if tx["txid"] in cache:
            continue
        new += 1
        if SRC not in {v.get("addr") for v in tx.get("vin", [])}:
            cache[tx["txid"]] = None  # 입금 거래는 기록만
            continue
        out = defaultdict(float)
        for vo in tx.get("vout", []):
            for a in vo.get("scriptPubKey", {}).get("addresses") or []:
                if a != SRC:  # 잔돈은 제외
                    out[a] += float(vo["value"])
        cache[tx["txid"]] = {"t": tx.get("time", 0), "out": out}
    print(f"page {page}: 신규 {new}/{len(txs)}")
    if not txs or page + 1 >= res.get("pagesTotal", 1) or (new == 0 and page > 0):
        break
    time.sleep(0.5)
save("txs_cache.json", cache)

# 2) 집계
rec, daily, big = defaultdict(float), defaultdict(float), []
for txid, v in cache.items():
    if not v:
        continue
    for a, amt in v["out"].items():
        rec[a] += amt
    if DST in v["out"]:
        day = time.strftime("%Y-%m-%d", time.gmtime(v["t"]))
        daily[day] += v["out"][DST]
        big.append({"txid": txid, "t": v["t"], "amount": v["out"][DST]})
total_out = sum(rec.values())
cum, series = 0, []
for day in sorted(daily):
    cum += daily[day]
    series.append({"d": day, "amount": daily[day], "cum": cum})
save("transfers.json", {
    "updated": int(time.time()), "src": SRC, "dst": DST, "observed": OBSERVED,
    "sent_to_dst": rec.get(DST, 0), "total_out": total_out,
    "recipients": [{"addr": a, "amount": x} for a, x in sorted(rec.items(), key=lambda k: -k[1])[:20]],
    "recipient_count": len(rec), "daily": series,
    "top_txs": sorted(big, key=lambda b: -b["amount"])[:30], "tx_count": len(big)})

# 3) 잔고 기록
bal = load("balances.json", [])
bal.append({"t": int(time.time()),
            "src": get(f"/addr/{SRC}/?noTxList=1")["balance"],
            "dst": get(f"/addr/{DST}/?noTxList=1")["balance"]})
save("balances.json", bal[-2000:])
print("완료: DST 이체 합계", rec.get(DST, 0))
