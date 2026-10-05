# research-docs

Fogify로 진행하는 **로컬 처리 vs 엣지 서버 오프로딩** 연구의 계획과 기록.
(`docs/`, `docs-code/`는 Fogify 원본 문서다. 내 문서는 여기에만 둔다.)

## 용어

- **로컬**: 작업을 만들어내는 기기 자신 (`local`)
- **엣지 서버**: 로컬 근처, 로컬과 클라우드 사이에 있는 서버 (`edge-server-1`, `edge-server-2`)
- **TCT**: Task Completion Time. 로컬에서 작업 시작부터 결과를 받을 때까지의 시간

## 문서

| # | 문서 | 내용 | 상태 |
|---|---|---|---|
| 01 | [01-uvc-sha256-plan.md](01-uvc-sha256-plan.md) | SHA-256 워크로드 실험 구현 계획, 주의점, 단계별 진행 상황 | 진행 중 (4/6단계 완료) |
| 02 | [02-uvc-sha256-baseline.md](02-uvc-sha256-baseline.md) | 원본 서버만 실행해서 iter별 계산 시간 측정 | ✅ |
| 03 | [03-uvc-sha256-fogify-deploy.md](03-uvc-sha256-fogify-deploy.md) | Fogify 배포 확인: CPU 제한, RTT 규칙, 액션, 모니터링 | ✅ |
| 04 | 04-uvc-sha256-results.md | 결과 정리 (6단계) | 예정 |

## 지금까지 알아낸 핵심 (빠른 참고)

| 항목 | 내용 | 출처 |
|---|---|---|
| 논문 iter=100 | 계산이 거의 0이라 의미 없음. **iter 100k~3M** 사용 | 02 |
| CPU 제한 | 느린 CPU가 아니라 **100ms마다의 할당량**. 짧은 작업에는 효과 없음 | 01 주의점 6 |
| Fogify CPU 계산 | `cores × clock_speed / CPU_FREQ(2086)`, 소수 첫째 자리로 반올림 | 03 |
| RTT | **로컬 쪽 delay + 엣지 서버 쪽 delay** (5+5 → 약 10ms) | 03 |
| stress 액션 | 컨테이너 안에서 `cpulimit` + `stress` 실행. `cpu`는 노드 CPU의 % | 03 |
| 사용자 지표 | `/fogify/metrics`는 현재 수집 안 됨 → **클라이언트 CSV가 주 결과** | 03 |
| SDK 시나리오 | `scenario_execution(name)`. `time`은 이전 액션 후 기다리는 초 | 03 |

## 관련 코드

| 경로 | 내용 |
|---|---|
| `examples/uvc-sha256/upstream/` | 원본 소스 (수정 없음) + NOTICE |
| `examples/uvc-sha256/app/` | Fogify용 앱 (`uvc-server`, `uvc-client`), 사용법은 `app/README.md` |
| `examples/uvc-sha256/docker-compose.yaml` | 토폴로지 (로컬 1, 엣지 서버 2) + 시나리오 3개 |
