# 01. SHA-256 워크로드로 로컬 vs 엣지 서버 TCT 실험 — 구현 계획

- 브랜치: `exp/uvc-sha256`
- 작성일: 2026-10-05 (같은 날 용어와 엣지 서버 2대 구성 반영)

## 용어

| 용어 | 뜻 | 코드/라벨 |
|---|---|---|
| **로컬** | 작업을 만들어내는 기기 자신 (IoT/모바일 기기) | `local` |
| **엣지 서버** | 로컬 근처에 있는 서버. 로컬과 클라우드 사이에 위치 | `edge-server-1`, `edge-server-2` |
| 클라우드 | 멀리 있는 서버 (이번 단계에서는 사용하지 않음) | `cloud` |

※ "엣지"라는 말만 단독으로 쓰지 않는다. 항상 **로컬** 또는 **엣지 서버**라고 쓴다.

## 목표

논문 *Unikernels vs. Containers* 의 SHA-256 워크로드를 가져와서, Fogify 위에서 같은 작업을 두 방식으로 처리해 비교한다.

- **로컬 처리** (`local`): 로컬이 직접 SHA-256을 계산
- **엣지 서버 오프로딩** (`edge-server`): 로컬이 엣지 서버로 요청을 보내고, 엣지 서버가 계산해서 결과를 돌려줌. **엣지 서버는 2대**를 둔다.

측정 지표는 **TCT (Task Completion Time)**. 로컬에서 작업 시작부터 결과를 받을 때까지의 시간이다.
실험 변수는 **로컬↔엣지 서버 RTT, 대역폭(BW), 엣지 서버 CPU 부하, 연산량(iter)**이다.

## 원본 정보

| 항목 | 내용 |
|---|---|
| 논문 | H. Dinh-Tuan, *Unikernels vs. Containers: A Runtime-Level Performance Comparison for Resource-Constrained Edge Workloads* (IEEE, arXiv:2509.07891) |
| 코드 | https://github.com/haidinhtuan/Unikernel-vs-Container (확인한 커밋: `4e00774`, 2026-04-02) |
| 라이선스 | Apache-2.0 (Fogify와 같음 → 출처를 남기면 가져다 써도 됨) |

### 원본 구성 (분석 결과)

| 폴더 | 내용 | 쓸지 |
|---|---|---|
| `go-compute-app/` | `POST /compute?iter=N`: 요청 body를 SHA-256으로 N번 반복 해시해서 반환 (:8080) | ⭐ 메인 |
| `go-http-app/` | `GET /hello`: 바로 응답 (I/O 워크로드) | 비교용 |
| `node-compute-app/`, `node-http-app/` | 같은 기능의 Node.js 버전 | 나중에 (선택) |
| `post.lua` | `wrk` 부하 도구용 POST 스크립트 (`payload.dat`를 body로 사용) | 참고 |
| `measure_*.sh` | 컨테이너 기동 시간 측정 | 안 씀 |
| `main`, `myapp` 등 | **미리 빌드된 바이너리 (약 130MB)** | ❌ 가져오지 않음 |

### 확인된 주의점

1. **반복 횟수 차이**: 논문에는 100회라고 되어 있지만, 코드의 기본값은 `iter=20000`이다. 실험할 때는 항상 iter를 명시한다.
2. **iter=100은 너무 가볍다** (2단계에서 확인: 계산 ≈ 0, 측정값은 HTTP 오버헤드뿐). 실험 범위는 **iter = 100k ~ 3M**으로 잡는다.
3. **`FROM scratch` 이미지**: 셸이 없다. Fogify용 이미지는 alpine을 베이스로 쓴다.
4. **유니커널(Nanos) 부분은 제외**: Fogify는 Docker 컨테이너만 다룬다. 원본은 "워크로드 출처"로만 쓴다.
5. **Fogify 사용자 지표 파일**: 문서에는 `fogify.metrics.json`이라고 되어 있지만, 실제 agent 코드(`utils/monitoring.py`)는 컨테이너 안의 **`/fogify/metrics`**를 읽는다. 또 `isnumeric()` 검사 때문에 **정수 값만** 받는다. → TCT를 µs 정수로 기록한다.
6. **CPU 제한은 "느린 CPU"가 아니라 "할당량"이다** (3단계에서 확인). Docker `--cpus`와 Fogify의 cgroup 제한은 100ms마다 정해진 양만 CPU를 쓰게 한다. 그래서 **짧은 작업은 제한을 받기 전에 끝나 버린다**. 실제로 iter=100k에서 0.5코어로 제한한 로컬(5.8ms)이 엣지 서버(7.4ms)보다 빨랐다. → 로컬이 느린 기기라는 효과가 나타나려면 **작업이 수십 ms 이상**이어야 한다. 4단계에서 Fogify의 `clock_speed` 제한도 같은 방식인지 확인한다.

## 폴더 구조

```
research-docs/                     ← 내 연구 문서 (계획, 결과 기록)
  01-uvc-sha256-plan.md            ← 이 문서
  02-uvc-sha256-baseline.md        ← 2단계: 원본 단독 실행 결과
examples/uvc-sha256/               ← Jupyter에서 examples/로 바로 보임
  upstream/                        ← 원본 소스 그대로 (바이너리 제외) + NOTICE
  app/                             ← Fogify용 앱 (이미지 1개로 서버와 클라이언트 둘 다)
    internal/work/                 ← SHA-256 반복 함수 (로컬과 엣지 서버가 같은 코드 사용)
    cmd/uvc-server/                ← 엣지 서버: /compute + 서버 계산 시간 헤더
    cmd/uvc-client/                ← 로컬: -mode local | edge-server, 작업마다 TCT를 CSV로 출력
  docker-compose.yaml              ← (4단계) services + x-fogify
  uvc-sha256.ipynb                 ← (5단계) 배포 → 실행 → 수집 → 그래프 → undeploy
```

※ 처음 계획은 `server/`와 `client/`를 따로 두는 것이었다. 같은 해시 코드를 공유하도록 `app/` 하나로 합쳤다.

## 토폴로지 (4단계 초안)

```
                 ┌──────────────── edge-net (RTT, BW 조절) ────────────────┐
                 │                                                         │
          ┌──────┴──────┐                                     ┌────────────┴───────────┐
          │   local     │ ── POST /compute ─────────────────▶ │ edge-server-1 (빠른 CPU) │
          │ (느린 CPU)  │ ── POST /compute ─────────────────▶ │ edge-server-2 (빠른 CPU) │
          │ uvc-client  │                                     │ uvc-server             │
          └─────────────┘                                     └────────────────────────┘
```

- 엣지 서버 2대는 처음에는 **같은 사양**으로 둔다. 각 엣지 서버와의 RTT를 다르게 주거나, 한 대에만 `stress`를 걸면 **어느 엣지 서버로 보낼지** 비교하는 실험으로 확장할 수 있다.
- 클라이언트는 `-servers`에 여러 개를 넣으면 순서대로 돌아가며 보낸다 (round-robin). 서버를 고르는 정책은 나중에 연구 주제로 바꿀 수 있다.

## 단계별 계획 (단계마다 커밋 1개)

| # | 단계 | 할 일 | 완료 기준 |
|---|---|---|---|
| 0 ✅ | 계획 | 브랜치 생성, `research-docs/`, 이 문서 | 이 문서 커밋 |
| 1 ✅ | 원본 가져오기 | `upstream/`에 소스만 복사, `NOTICE.md` 작성 | 바이너리 없이 커밋 |
| 2 ✅ | 원본 단독 실행 | Fogify 없이 빌드하고 `--cpus 1 --memory 128m`으로 실행, iter별 시간 측정 | [02-uvc-sha256-baseline.md](02-uvc-sha256-baseline.md) |
| 3 ✅ | Fogify용 앱 | `app/`: 공용 해시 함수, `uvc-server`(서버 계산 시간 헤더), `uvc-client`(`local`/`edge-server` 모드, CSV 출력, `/fogify/metrics`). 이미지 `uvc-sha256:0.1` | Fogify 없이 로컬 1 + 엣지 서버 2로 두 모드 모두 동작 확인 (`app/README.md`) |
| 4 | 토폴로지 | compose 작성. **nodes**: local(낮은 CPU, 256~512M), edge-server(2코어, 1~2G). **networks**: 로컬↔엣지 서버 (기본 RTT 10ms, BW 100Mbps). **topology**: local 1, edge-server-1, edge-server-2. **scenarios**: RTT 단계 증가 / BW 단계 감소 / 엣지 서버 `stress`. 배포 후 `ping`으로 RTT 실측, `clock_speed` 효과 확인 | `fogify.deploy()` 성공, RTT 실측값 일치 |
| 5 | 노트북 | deploy → `docker exec`로 로컬 처리와 엣지 서버 오프로딩 실행 → 시나리오 → CSV 수집 → 그래프 (TCT vs RTT, BW, 엣지 서버 부하, iter) → undeploy | 그래프 출력 |
| 6 | 결과 정리 | `research-docs/03-uvc-sha256-results.md`: 설정, 그래프, 로컬 처리와 엣지 서버 오프로딩이 역전되는 지점 | 문서 커밋 |

## 실험 변수 (초안)

| 변수 | 값 | 조절 방법 |
|---|---|---|
| RTT (로컬↔엣지 서버) | 2 / 10 / 50 / 100 / 200 ms | `networks` 지연 (양방향에 절반씩), 시나리오 `update_network` |
| BW | 1 / 10 / 100 Mbps | `networks` bandwidth |
| 엣지 서버 CPU 부하 | 0 / 50 / 90 % | 시나리오 `stress` |
| 연산량 | iter = 100 / 100k / 1M / 3M | 클라이언트 `-iter` |
| payload | 1 KB / 100 KB / 1 MB | 클라이언트 `-payload` (BW 영향이 보이게) |
| 로컬 사양 | 1코어 이하, clock_speed로 성능 낮춤 | `nodes` |
| 연결 방식 | keep-alive 사용 / 작업마다 새 연결 | 클라이언트 `-keepalive` (새 연결이면 RTT가 1번 더 붙음) |

각 조건마다 작업 N회 (예: 50~100회)를 실행하고 **중앙값, p95**로 비교한다.

## 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| CPU 제한이 할당량 방식이라 짧은 작업에는 효과가 없음 (주의점 6) | iter를 1M 이상으로 쓰거나, 작업 간 간격 없이 연속 실행. 4단계에서 Fogify의 cgroup 설정 확인 |
| tc 지연이 Swarm 오버레이에서 의도대로 적용되는지 | 4단계에서 로컬 노드에서 `ping edge-server-1`로 RTT 실측 |
| 노트북 PC 한 대라 로컬과 엣지 서버가 같은 CPU를 나눠 씀 | 총 할당 코어를 16스레드보다 충분히 작게 잡고, 다른 무거운 작업은 끈 상태에서 측정 |
| `/fogify/metrics` 수집이 실제로 되는지 (agent가 컨테이너 파일 경로에 접근할 수 있는지 불확실) | CSV(stdout)를 주 결과로 쓰고, metrics는 보조 자료로만 사용 |
