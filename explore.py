#!/usr/bin/env python3
"""주소 탐색기: python explore.py <주소> [<주소> ...]
각 주소의 잔고, 입금 출처 상위 10, 출금처 상위 10을 보여준다. 이전 단계의 집합과 겹치면 표시한다."""
import json, os, sys, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
PAGE_SIZE, RVN = 50, 1e8
MAX_PAGES = int(os.environ.get("MAX_PAGES", "200"))
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

def jl(n, d):
    p = os.path.join(D, n)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d

T = jl("transfers.json", {}); EXT = jl("ext_all.json", {})
H = jl("hop2.json", {}); GROUP = {r["addr"] for r in H.get("rows", [])}
def tag(a):
    if a == T.get("src"): return " [과거 1위]"
    if a == T.get("dst"): return " [현재 1위]"
    if a in GROUP: return " [14개 분할주소]"
    if a in EXT: return f" [14개 주소 수신자, 받은 {EXT[a]:,.0f}]"
    return ""

def dr(r):
    f = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t)) if t else "-"
    return f"{f(r[0])}~{f(r[1])}" if r else ""

def scan(addr, flt, side):
    agg, ts, page, n = defaultdict(float), {}, 1, 0
    def mark(a, t):
        x = ts.setdefault(a, [t, t]); x[0] = min(x[0], t); x[1] = max(x[1], t)
    while page <= MAX_PAGES:
        txs = get(f"/address/{addr}?details=txs&filter={flt}&page={page}&pageSize={PAGE_SIZE}").get("transactions") or []
        for tx in txs:
            t = tx.get("blockTime", 0)
            senders = {a for v in tx.get("vin", []) for a in (v.get("addresses") or [])}
            if side == "in":   # 입금: addr가 입력이 아닌 거래만
                if addr in senders: continue
                amt = sum(int(vo["value"]) for vo in tx.get("vout", []) if addr in (vo.get("addresses") or [])) / RVN
                for s in senders: agg[s] += amt / max(len(senders), 1); mark(s, t)
            else:              # 출금: addr가 입력인 거래의 다른 주소 출력
                if addr not in senders: continue
                for vo in tx.get("vout", []):
                    for d in vo.get("addresses") or []:
                        if d != addr: agg[d] += int(vo["value"]) / RVN; mark(d, t)
            n += 1
        if len(txs) < PAGE_SIZE: return agg, ts, n, True
        page += 1; time.sleep(0.5)
    return agg, ts, n, False

for addr in sys.argv[1:]:
    b = get(f"/address/{addr}?details=basic")
    print(f"\n===== {addr}{tag(addr)}")
    print(f"잔고 {int(b['balance'])/RVN:,.0f} / 누적수신 {int(b.get('totalReceived',0))/RVN:,.0f} / 거래 {b.get('txs')}건")
    for title, flt, side in (("입금 출처", "outputs", "in"), ("출금처", "inputs", "out")):
        agg, ts, n, done = scan(addr, flt, side)
        print(f"-- {title} 상위 10 (서로 다른 주소 {len(agg):,}개, {'전체' if done else '일부만'} 조회)")
        for a, x in sorted(agg.items(), key=lambda k: -k[1])[:10]:
            print(f"{a}  {x:,.0f}  {dr(ts.get(a))}{tag(a)}")
