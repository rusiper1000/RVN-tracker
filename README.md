# 레이븐코인 지갑 이동 추적기

- `index.html`: 과거 1위 → 현재 1위 이체 추적 대시보드 (`data/*.json` 읽음)
- `lineage.html`: 업비트 지갑 계보와 2026 대이동 정리 페이지 (데이터 파일 불필요)
- `collector.py` → `trace2.py` → `trace3.py`: 수집·분석 순서. `explore.py`, `first_seen.py`, `daily.py`: 주소 단위 조회 도구
- `monitor.py`: 감시 목록 5개 주소의 대규모 이동을 `data/watch.json`에 기록 (index.html 하단에 표시)
- `.github/workflows/collect.yml`: collector.py와 monitor.py를 6시간마다 실행해 `data/`를 갱신

로컬 확인: `python -m http.server 8000` 후 http://localhost:8000
