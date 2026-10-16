#!/usr/bin/env python3
"""일별 입출금 추이: python daily.py <주소> [일수=45]
상장폐지(2026-10-12 15:00 KST = 06:00 UTC) 전후로 입금/출금이 어떻게 달라졌는지 본다. 날짜는 UTC 기준."""
import json, os, sys, time, calendar, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
PAGE_SIZE, RVN = 50, 1e8
MAX_PAGES = int(os.environ.get("MAX_PAGES", "800"))
DELIST = calendar.timegm((2026, 10, 12, 6, 0, 0))
addr = sys.argv[1]; days = int(sys.argv[2]) if len(sys.argv) > 2 else 45
now = int(time.time()); cutoff = now - days * 86400

def get(path):
    for i in range(4):
        try:
            rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("재시도:", e, file=sys.stderr); time.sleep(3 * (i + 1))
    sys.exit("API 호출 실패")

rows = defaultdict(lambda: [0, 0.0, 0, 0.0])  # 입금 건수, 입금량, 출금 건수, 출금량
tot = {"before": [0.0, 0.0], "after": [0.0, 0.0]}
done = False
for page in range(1, MAX_PAGES + 1):
    txs = get(f"/address/{addr}?details=txs&page={page}&pageSize={PAGE_SIZE}").get("transactions") or []
    for tx in txs:
        t = tx.get("blockTime") or now
        if t < cutoff:
            done = True; break
        senders = {a for v in tx.get("vin", []) for a in (v.get("addresses") or [])}
        d, k = time.strftime("%Y-%m-%d", time.gmtime(t)), ("after" if t >= DELIST else "before")
        if addr in senders:  # 출금: 자기 주소(잔돈)를 뺀 출력
            amt = sum(int(vo["value"]) for vo in tx.get("vout", []) if addr not in (vo.get("addresses") or [])) / RVN
            rows[d][2] += 1; rows[d][3] += amt; tot[k][1] += amt
        else:                # 입금
            amt = sum(int(vo["value"]) for vo in tx.get("vout", []) if addr in (vo.get("addresses") or [])) / RVN
            rows[d][0] += 1; rows[d][1] += amt; tot[k][0] += amt
    print(f"page {page}…", file=sys.stderr, flush=True)
    if done or len(txs) < PAGE_SIZE:
        break
    time.sleep(0.4)

print(f"\n{addr}  (최근 {days}일, UTC 기준, 상장폐지=2026-10-12 06:00 UTC)")
print("날짜        입금건수   입금량(RVN)   출금건수   출금량(RVN)")
for d in sorted(rows):
    r = rows[d]
    mark = "  <- 상장폐지일" if d == "2026-10-12" else ""
    print(f"{d}  {r[0]:8,}  {r[1]:14,.0f}  {r[2]:8,}  {r[3]:14,.0f}{mark}")
print(f"\n상장폐지 시각 이전 합계: 입금 {tot['before'][0]:,.0f} / 출금 {tot['before'][1]:,.0f}")
print(f"상장폐지 시각 이후 합계: 입금 {tot['after'][0]:,.0f} / 출금 {tot['after'][1]:,.0f}")
if not done:
    print("주의: MAX_PAGES에서 멈춰 가장 오래된 날짜는 일부만 포함될 수 있습니다.")
