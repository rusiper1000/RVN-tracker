#!/usr/bin/env python3
"""과거 1위 주소(SRC) -> 현재 1위 주소(DST) 이체 추적기 (Blockbook API v2).
다른 Blockbook 서버를 쓰려면 RVN_API 환경변수만 바꾸면 된다."""
import json, os, sys, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
SRC = "RRGYxRYGhvUuXBpvypLK9YdaXDk6Gs95LS"   # 과거 1위 (업비트 추정)
DST = "R9J3tqF6rXFQVUrrMxtkMBjgeobPmxLwXn"   # 현재 1위
OBSERVED = 5527986869.06                     # 스크린샷상 DST 증가분(RVN)
MAX_PAGES = int(os.environ.get("MAX_PAGES", "300"))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "50"))
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(D, exist_ok=True)
RVN = 1e8  # Blockbook 금액은 사토시 단위 문자열

def get(path):
    for i in range(4):
        try:
            rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("재시도:", path, e, file=sys.stderr); time.sleep(3 * (i + 1))
    sys.exit("API 호출 실패: " + path)

def load(name, default):
    p = os.path.join(D, name)
    return json.load(open(p)) if os.path.exists(p) else default

def save(name, obj):
    json.dump(obj, open(os.path.join(D, name), "w"), ensure_ascii=False)

# 1) 거래 수집 (최신순, filter=inputs: SRC가 입력으로 쓰인 출금 거래만)
cache = load("txs_cache.json", {})
state = load("state.json", {"complete": False})  # 첫 전체 수집이 끝난 뒤에만 조기 종료 허용
finished = False
for page in range(1, MAX_PAGES + 1):
    res = get(f"/address/{SRC}?details=txs&filter=inputs&page={page}&pageSize={PAGE_SIZE}")
    txs = res.get("transactions") or []
    new = 0
    for tx in txs:
        if tx["txid"] in cache:
            continue
        new += 1
        if not any(SRC in (v.get("addresses") or []) for v in tx.get("vin", [])):
            cache[tx["txid"]] = None
            continue
        out = defaultdict(float)
        for vo in tx.get("vout", []):
            for a in vo.get("addresses") or []:
                if a != SRC:  # 잔돈 제외
                    out[a] += int(vo["value"]) / RVN
        cache[tx["txid"]] = {"t": tx.get("blockTime", 0), "out": out}
    print(f"page {page}: 신규 {new}/{len(txs)} (누적 {len(cache)}건)", flush=True)
    if page % 20 == 0:
        save("txs_cache.json", cache)  # 중간 저장
    if len(txs) < PAGE_SIZE or (state["complete"] and new == 0):
        finished = True  # 끝까지 도달(totalPages는 -1로 올 수 있어 신뢰하지 않음)
        break
    time.sleep(0.5)
save("txs_cache.json", cache)
if finished:
    state["complete"] = True
    save("state.json", state)
else:
    print(f"주의: MAX_PAGES({MAX_PAGES})에서 멈췄습니다. 더 오래된 거래가 남아 있으니 MAX_PAGES 값을 올려 다시 실행하세요. (예: set MAX_PAGES=2000)")

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
            "src": int(get(f"/address/{SRC}?details=basic")["balance"]) / RVN,
            "dst": int(get(f"/address/{DST}?details=basic")["balance"]) / RVN})
save("balances.json", bal[-2000:])
print("완료: DST 이체 합계", rec.get(DST, 0))
