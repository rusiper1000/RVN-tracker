#!/usr/bin/env python3
"""현재 1위(DST)로 들어온 자금의 출처 분석.
trace2.py가 만든 data/ext_all.json(14개 주소의 외부 수신자 집합)과 DST의 송금 주소가 얼마나 겹치는지 계산한다."""
import json, os, sys, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
PAGE_SIZE, RVN = 50, 1e8
MAX_PAGES = int(os.environ.get("MAX_PAGES", "400"))
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def get(path):
    for i in range(4):
        try:
            rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("재시도:", path, e, file=sys.stderr); time.sleep(3 * (i + 1))
    sys.exit("API 호출 실패: " + path)

DST = json.load(open(os.path.join(D, "transfers.json"), encoding="utf-8"))["dst"]
ext = json.load(open(os.path.join(D, "ext_all.json")))
total = matched = 0.0
tx_in = tx_match = 0
by_sender, t_min, t_max, complete = defaultdict(float), 0, 0, False
for page in range(1, MAX_PAGES + 1):
    txs = get(f"/address/{DST}?details=txs&filter=outputs&page={page}&pageSize={PAGE_SIZE}").get("transactions") or []
    for tx in txs:
        senders = {a for v in tx.get("vin", []) for a in (v.get("addresses") or [])}
        if DST in senders:
            continue  # DST가 입력인 거래(잔돈 순환)는 제외
        amt = sum(int(vo["value"]) for vo in tx.get("vout", []) if DST in (vo.get("addresses") or [])) / RVN
        if amt <= 0:
            continue
        total += amt; tx_in += 1
        t = tx.get("blockTime", 0); t_min = min(t_min or t, t); t_max = max(t_max, t)
        hit = any(s in ext for s in senders)
        if hit:
            matched += amt; tx_match += 1
        for s in senders:
            by_sender[s] += amt / max(len(senders), 1)
    print(f"page {page}: 누적 입금 {total:,.0f} (겹침 {matched:,.0f})", flush=True)
    if len(txs) < PAGE_SIZE:
        complete = True; break
    time.sleep(0.5)
top = sorted(by_sender.items(), key=lambda k: -k[1])[:10]
json.dump({"updated": int(time.time()), "complete": complete, "total_in": total, "matched_in": matched,
           "tx_in": tx_in, "tx_match": tx_match, "senders": len(by_sender)},
          open(os.path.join(D, "dst_sources.json"), "w"))
print(f"\n{'전체 조회' if complete else 'MAX_PAGES에서 중단(최근 거래만 포함)'}")
print(f"현재 1위 입금 {tx_in:,}건 / {total:,.0f} RVN")
print(f"14개 주소의 수신자와 겹치는 송금: {tx_match:,}건 / {matched:,.0f} RVN ({matched/max(total,1)*100:.1f}%)")
print(f"서로 다른 송금 주소 {len(by_sender):,}개. 상위 10:")
for a, x in top:
    print(f"{a}  {x:,.0f}  {'(겹침)' if a in ext else ''}")
