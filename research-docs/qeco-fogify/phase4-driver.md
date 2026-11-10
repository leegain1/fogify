# Phase 4. Fogify 연결: 정책이 작업마다 실행 위치를 고르게

## 구조

```
 ui 컨테이너 (Jupyter)                          제어용 네트워크 fogemulator_default
 ┌──────────────────────────┐   POST /act   ┌──────────────────────────────┐
 │ driver.py                │ ────────────▶ │ qeco-policy (qeco-tf:0.1)    │
 │  - 정책 선택              │               │ policy_server.py :8090       │
 │  - 관측 스레드 (0.5초)     │               │ QECO-orig / QECO-net 모델     │
 │  - CSV 기록              │               └──────────────────────────────┘
 └──────────┬───────────────┘
            │ POST /run?target=local|edge1|edge2   GET /probe?target=edge1
            ▼
 ┌──────────────────────────┐  edge-server-net-1 ──▶ edge-server-1 (/compute)
 │ local: uvc-client agent  │  edge-server-net-2 ──▶ edge-server-2
 │ :8081 (TCT는 여기서 잼)    │
 └──────────────────────────┘
 cAdvisor (:8080) ◀── driver: 엣지 서버 컨테이너 CPU 사용량
```

| 구성 | 내용 |
|---|---|
| `uvc-client agent` (Go, 이미지 `uvc-sha256:0.2`) | 로컬 컨테이너 안의 HTTP 서버. `/run`은 요청한 위치에서 작업을 실제로 실행하고 `{tct_ms, server_compute_ms, status}`를 돌려준다. 작업은 한 번에 하나씩 실행한다 |
| 제어용 네트워크 | 배포 후 로컬 컨테이너를 `fogemulator_default`에 연결한다 (`docker network connect`). tc 규칙이 걸린 엣지 서버 네트워크를 거치지 않으므로, 드라이버 통신이 측정을 방해하지 않는다 |
| `qeco_sim/policy_server.py` | TF가 있는 컨테이너에서 QECO 모델을 띄운다. ui 컨테이너(Python 3.11)에는 TF가 없기 때문이다 |
| `driver.py` | 관측 → 정책 → agent 호출 → CSV 기록 |

기존 실험(A~E)은 이미지 `uvc-sha256:0.1`을 그대로 쓴다. agent 모드는 `uvc-client`에 하위 명령으로만 추가했다 (`cmd/uvc-client/agent.go`).

## 상태 관측

| 상태 | 방법 | 주기 / 지연 |
|---|---|---|
| RTT_i | agent `/probe` → 엣지 서버 `GET /hello` 왕복 시간 (keep-alive) | 0.5초 |
| B_i | 드라이버가 설정한 값 (`set_link`) | 즉시 |
| L_i | cAdvisor CPU 사용량(최근 두 샘플, 약 1초 간격) − 우리 작업의 연산 시간, ÷ 2코어 | 약 1~2초 늦음 |
| 최근 TCT | CSV에 기록 | - |

**QECO 상태 만들기**
- 시뮬레이터와 같은 형식으로 만든다: `[크기/64KB, 로컬 큐, 전송 큐, 엣지 서버 큐 ×2, 1] (+ RTT/100, log10(B)/2, L)`.
- 작업을 하나씩 실행하므로 **큐 값은 결정 시점에 항상 0**이다.
- LSTM 입력은 지난 결정 이후 흐른 시간(10 ms당 1칸, 최대 10칸)만큼 현재 값을 넣는다.

**버그 수정:** 처음에는 `/probe`가 응답 본문을 다 읽지 않고 닫아서 매번 새로 연결했다. 그래서 RTT가 약 22 ms(실제의 2배)로 관측됐다. 본문을 다 읽도록 고친 뒤 관측 RTT p50은 10.7~11.0 ms다.

## 비교 정책

| 정책 | 구현 |
|---|---|
| Always-Local / Edge1 / Edge2 | 고정 |
| Nearest-Edge | 관측 RTT가 가장 작은 엣지 서버 |
| Model-Greedy | T_edge,i = T_comp(L_i) + RTT_i + D/B_i + 0.9, T_local = 140 ms (평균식) → 가장 작은 곳 |
| QECO-orig / QECO-net | Phase 3에서 학습한 모델 (정책 서버) |
| Oracle | 작업마다 세 위치를 모두 실측하고 가장 빠른 곳 (사후 기준선) |

**작업 실행 방식**
- 작업은 하나씩 보낸다.
- 작업 사이 쉬는 시간은 평균 200 ms 지수분포다. 같은 시드를 쓰므로 모든 정책이 같은 간격 순서를 쓴다.
- 조건마다 워밍업 1개 뒤 n = 30을 기록한다.

## 결과: 기본 조건 (RTT 10 ms, 100Mbit, 부하 0, iter 1M, 1 KB, n = 30)

| 정책 | p50 | p95 | 평균 | 로컬 / E1 / E2 비율 | 결정 시간 |
|---|---|---|---|---|---|
| Always-Local | 97.5 | 129.1 | 100.2 | 1 / 0 / 0 | 1.4 ms |
| Always-Edge1 | 82.6 | 83.6 | 82.2 | 0 / 1 / 0 | 1.5 |
| Always-Edge2 | 82.6 | 84.1 | 82.1 | 0 / 0 / 1 | 1.5 |
| Nearest-Edge | 82.9 | 84.3 | 82.3 | 0 / .40 / .60 | 1.4 |
| Model-Greedy | 82.6 | 84.8 | 82.3 | 0 / .17 / .83 | 1.2 |
| QECO-orig | 90.6 | 124.9 | 95.3 | 1 / 0 / 0 | 6.8 |
| QECO-net | 92.9 | 121.7 | 96.3 | 1 / 0 / 0 | 6.0 |
| Oracle | 78.0 | 79.3 | 75.2 | .50 / .23 / .27 | - |

- **완료 기준 통과:** 모든 정책이 기본 조건에서 끝까지 돌았고, 에러는 0건이다. CSV는 `results/P4_baseline.csv`, 요약은 `P4_baseline_summary.csv`다.
- **로컬 처리:** 쉬는 시간이 있어서 평균 100 ms다 (연속 실행이면 약 150 ms). 그래도 엣지 서버(82 ms)보다 느리다.
- **Oracle:** 절반은 로컬을 고른다. 할당량이 남아 있어 로컬이 70 ms 근처로 끝나는 작업이 있기 때문이다.

## 발견: QECO가 테스트베드에서 "항상 로컬"을 고른다

같은 상태를 넣고 QECO-net의 Q값을 확인했다 (높을수록 좋음).

| 상태 | Q(로컬) | Q(E1) | Q(E2) |
|---|---|---|---|
| 로컬 큐 0, RTT 10 ms | **−14.2** | −16.4 | −16.7 |
| 로컬 큐 0, RTT 105 ms | **−14.4** | −16.2 | −16.1 |
| 로컬 큐 3슬롯, RTT 10 ms | −15.6 | **−14.7** | −16.8 |

- **QECO-net이 배운 규칙:** RTT를 거의 보지 않고 "**로컬 큐가 비어 있으면 로컬, 차 있으면 엣지 서버**"를 배웠다.
- **시뮬레이터에서 통한 이유:** 학습 때 작업이 무작위로 도착해서 로컬 큐가 자주 찼다. 큐가 비어 있을 때는 로컬이 CFS 할당량 덕분에 70~120 ms로 빨랐다.
- **테스트베드에서 안 통하는 이유:** 작업을 하나씩 보내므로 큐가 늘 비어 있다. 그래서 항상 로컬을 고르고, 엣지 서버 정책보다 10~14 ms 느리다.
- **원인 정리:** 작업 도착 방식이 학습 환경(open-loop, 큐 생김)과 실행 환경(closed-loop, 큐 없음)에서 달라서 생긴 **sim-to-testbed gap**이다. 상태 설계(큐 위주)와 보상이 이 차이에 민감하다는 것을 보여 준다.

## 실행 방법

```bash
docker build -t uvc-sha256:0.2 examples/uvc-sha256/app
docker exec -w /home/jovyan/examples/qeco-fogify fogemulator-ui-1 python phase4_baseline.py   # 약 6분
```

정책 서버는 드라이버가 `docker run`으로 띄운다. 호스트 경로가 다르면 `QECO_HOST_DIR`을 바꾼다.
