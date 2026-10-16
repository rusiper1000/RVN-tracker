#!/usr/bin/env python3
"""감시 목록 주소의 최근 이동을 기록한다 (4~6시간 간격 실행용, Blockbook API v2).
결과: data/watch.json (사이트가 읽음), data/watch_seen.json (처리한 거래 기록)"""
import json, os, time, urllib.request
from collections import defaultdict

API = os.environ.get("RVN_API", "https://blockbook.ravencoin.org/api/v2").rstrip("/")
DAYS = int(os.environ.get("DAYS", "14"))            # 첫 실행 때 거슬러 올라갈 일수
MAX_PAGES = int(os.environ.get("MAX_PAGES", "250"))  # 주소당 최대 페이지(50건/페이지)
PAGE_SIZE, RVN = 50, 1e8
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(D, exist_ok=True)

# in_min/out_min: 이 수량 이상의 입금/출금 거래만 '대규모 이동'으로 기록 (RVN)
WATCH = {
    "R9J3tqF6rXFQVUrrMxtkMBjgeobPmxLwXn": {"label": "현재 1위", "role": "콜드월렛 추정", "in_min": 5e7, "out_min": 1},
    "RNqSvKnzEzBgt9rUvaWCPBTyNtZRogEpo2": {"label": "RNqSvK", "role": "핫월렛 추정", "in_min": 1e8, "out_min": 1e8},
    "RDN1XKwt24hziyfWQbqFdtrVN1CHuY32eT": {"label": "현재 2위", "role": "휴면 콜드 추정", "in_min": 1, "out_min": 1},
    "RDQheYZszh52cGZgYuzSE5SbzwTeEzR4Jn": {"label": "현재 6위", "role": "휴면 콜드 추정", "in_min": 1, "out_min": 1},
    "RRGYxRYGhvUuXBpvypLK9YdaXDk6Gs95LS": {"label": "과거 1위", "role": "업비트", "in_min": 1e8, "out_min": 1e8},
}

def get(path):
    for i in range(4):
        try:
            rq = urllib.request.Request(API + path, headers={"User-Agent": "rvn-tx-tracker"})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("재시도:", path[:60], e); time.sleep(3 * (i + 1))
    return None

def load(n, default):
    p = os.path.join(D, n)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default

def save(n, obj):
    json.dump(obj, open(os.path.join(D, n), "w", encoding="utf-8"), ensure_ascii=False)

now = int(time.time()); cutoff = now - DAYS * 86400
W, seen = load("watch.json", {}), load("watch_seen.json", {})
events, daily, balances = W.get("events", []), W.get("daily", {}), W.get("balances", [])
wallets, snap = [], {"t": now}

for addr, m in WATCH.items():
    b = get(f"/address/{addr}?details=basic")
    if not b:
        print("건너뜀:", m["label"]); continue
    bal = int(b["balance"]) / RVN; snap[addr] = bal
    wallets.append({"addr": addr, "label": m["label"], "role": m["role"], "balance": bal})
    known, new_ids, new_ev, new_daily = set(seen.get(addr, [])), [], [], defaultdict(lambda: [0.0, 0.0])
    ok = True
    for page in range(1, MAX_PAGES + 1):
        res = get(f"/address/{addr}?details=txs&page={page}&pageSize={PAGE_SIZE}")
        if res is None:
            ok = False; break
        txs, stop = res.get("transactions") or [], False
        for tx in txs:
            t = tx.get("blockTime") or now
            if t < cutoff or tx["txid"] in known:
                stop = True; break
            vin = tx.get("vin", [])
            senders = {a for v in vin for a in (v.get("addresses") or [])}
            if addr in senders:  # 출금: 자기 주소(잔돈)를 뺀 출력
                outs = defaultdict(float)
                for vo in tx.get("vout", []):
                    for a in vo.get("addresses") or []:
                        if a != addr: outs[a] += int(vo["value"]) / RVN
                amt, kind = sum(outs.values()), "out"
                cp = max(outs, key=outs.get) if outs else ""
            else:                # 입금
                amt = sum(int(vo["value"]) for vo in tx.get("vout", []) if addr in (vo.get("addresses") or [])) / RVN
                kind = "in"
                top = max(vin, key=lambda v: int(v.get("value") or 0), default=None)
                cp = ((top or {}).get("addresses") or [""])[0]
            new_ids.append(tx["txid"])
            new_daily[time.strftime("%Y-%m-%d", time.gmtime(t))][0 if kind == "in" else 1] += amt
            if amt > 0 and amt >= m["in_min" if kind == "in" else "out_min"]:
                new_ev.append({"t": t, "addr": addr, "label": m["label"], "dir": kind, "amount": amt, "txid": tx["txid"], "cp": cp})
        if stop or len(txs) < PAGE_SIZE:
            break
        time.sleep(0.4)
    if not ok:
        print("수집 중단(다음 실행에서 다시 시도):", m["label"]); continue
    seen[addr] = (new_ids + seen.get(addr, []))[:500]
    events += new_ev
    d = daily.setdefault(addr, {})
    for day, (i, o) in new_daily.items():
        x = d.setdefault(day, [0.0, 0.0]); x[0] += i; x[1] += o
    for day in sorted(d)[:-45]:
        del d[day]
    print(f"{m['label']}: 잔고 {bal:,.0f} / 새 거래 {len(new_ids)}건 / 대규모 이동 {len(new_ev)}건", flush=True)

uniq = {(e["txid"], e["addr"]): e for e in events}
events = sorted(uniq.values(), key=lambda e: -e["t"])[:300]
if len(snap) > 1:
    balances = (balances + [snap])[-1500:]
save("watch.json", {"updated": now, "wallets": wallets, "events": events, "daily": daily, "balances": balances})
save("watch_seen.json", seen)
print("완료. 기록된 대규모 이동", len(events), "건")
