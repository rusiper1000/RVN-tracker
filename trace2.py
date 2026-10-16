#!/usr/bin/env python3
"""2단계 추적: 과거 1위가 쪼개 보낸 주소들의 현재 잔고와 이후 출금처를 조사한다.
collector.py를 먼저 실행해 data/transfers.json, data/txs_cache.json이 있어야 한다."""
import json, os, sys, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
MIN_RVN = float(os.environ.get("MIN_RVN", "1e8"))   # 이 수량 이상 받은 주소만 추적
PAGE_SIZE, MAX_PAGES, RVN = 50, int(os.environ.get("MAX_PAGES", "100")), 1e8
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

T = json.load(open(os.path.join(D, "transfers.json"), encoding="utf-8"))
cache = json.load(open(os.path.join(D, "txs_cache.json"), encoding="utf-8"))
DST = T["dst"]
targets = [r["addr"] for r in T["recipients"] if r["amount"] >= MIN_RVN]

span = {}  # 과거 1위로부터 받은 최초/최종 시각
for v in cache.values():
    for a, x in ((v or {}).get("out") or {}).items():
        if a in targets:
            s = span.setdefault(a, [v["t"], v["t"]])
            s[0], s[1] = min(s[0], v["t"]), max(s[1], v["t"])

infos = {}
def info(a):
    if a not in infos:
        r = get(f"/address/{a}?details=basic")
        infos[a] = {"bal": int(r["balance"]) / RVN, "recv": int(r.get("totalReceived", 0)) / RVN}
        time.sleep(0.3)
    return infos[a]
bal = lambda a: info(a)["bal"]

rows, ext_all, tset = [], defaultdict(float), set(targets)
for n, a in enumerate(targets, 1):
    out, page, tmin, tmax, ntx = defaultdict(float), 1, 0, 0, 0
    while page <= MAX_PAGES:
        txs = get(f"/address/{a}?details=txs&filter=inputs&page={page}&pageSize={PAGE_SIZE}").get("transactions") or []
        for tx in txs:
            if not any(a in (v.get("addresses") or []) for v in tx.get("vin", [])):
                continue
            ntx += 1
            t = tx.get("blockTime", 0); tmin = min(tmin or t, t); tmax = max(tmax, t)
            for vo in tx.get("vout", []):
                for d in vo.get("addresses") or []:
                    if d != a:
                        out[d] += int(vo["value"]) / RVN
        if len(txs) < PAGE_SIZE:
            break
        page += 1; time.sleep(0.5)
    internal = sum(x for d, x in out.items() if d in tset)
    ext = {d: x for d, x in out.items() if d not in tset}
    for d, x in ext.items():
        ext_all[d] += x
    received = next(r["amount"] for r in T["recipients"] if r["addr"] == a)
    rows.append({"addr": a, "received": received, "first_t": span.get(a, [0, 0])[0], "last_t": span.get(a, [0, 0])[1],
                 "out_first": tmin, "out_last": tmax, "balance": bal(a), "total_received": info(a)["recv"], "sent_internal": internal, "tx_out": ntx, "ext_distinct": len(ext),
                 "sent_external": sum(ext.values()), "sent_to_dst": out.get(DST, 0)})
    print(f"{n}/{len(targets)} {a[:10]}… 내부이동 {internal:,.0f} / 외부 {sum(ext.values()):,.0f} / 잔고 {rows[-1]['balance']:,.0f} / 전체수신 {rows[-1]['total_received']:,.0f}", flush=True)

json.dump(ext_all, open(os.path.join(D, "ext_all.json"), "w"))  # trace3.py가 사용
ext_top = [{"addr": d, "amount": x, "balance": bal(d)} for d, x in sorted(ext_all.items(), key=lambda k: -k[1])[:20]]
tot = lambda k: sum(r[k] for r in rows)
json.dump({"updated": int(time.time()), "dst": DST, "rows": rows, "ext_top": ext_top,
           "totals": {"received": tot("received"), "total_received": tot("total_received"), "balance": tot("balance"), "sent_internal": tot("sent_internal"),
                      "sent_external": tot("sent_external"), "tx_out": tot("tx_out"), "ext_distinct": len(ext_all),
                      "top20_share": sum(d["amount"] for d in ext_top) / max(sum(ext_all.values()), 1), "sent_to_dst": tot("sent_to_dst")}},
          open(os.path.join(D, "hop2.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("완료. 현재 1위로 간 합계:", tot("sent_to_dst"))
print(f"출금 트랜잭션 {tot('tx_out'):,}건 / 서로 다른 외부 수신 주소 {len(ext_all):,}개 / 상위20 비중 {sum(d['amount'] for d in ext_top)/max(sum(ext_all.values()),1)*100:.1f}%")
print("--- 외부 수신 상위 10 (받은 수량 / 현재 잔고) ---")
for d in ext_top[:10]:
    print(f"{d['addr']}  {d['amount']:,.0f} / {d['balance']:,.0f}")
