# 01. SHA-256 워크로드로 Local vs Edge TCT 실험 — 구현 계획

- 브랜치: `exp/uvc-sha256`
- 작성일: 2026-10-05

## 목표

논문 *Unikernels vs. Containers* 의 SHA-256 워크로드를 가져와서 Fogify 위에서 다음을 비교한다.

- **Local**: 기기(Device)가 직접 SHA-256을 계산
- **Edge**: 기기가 엣지 서버로 요청을 보내고, 엣지가 계산해서 결과를 돌려줌

측정 지표는 **TCT (Task Completion Time)**. 요청 시작부터 결과 수신까지의 시간이다.
실험 변수는 **RTT, 대역폭(BW), 엣지 CPU 부하**다.

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

### 미리 확인한 주의점

1. **반복 횟수 차이**: 논문에는 100회라고 되어 있지만, 코드의 기본값은 `iter=20000`이다. 실험할 때는 항상 `?iter=`를 명시한다.
2. **iter=100은 너무 가볍다**: 계산이 수십 µs 수준이라 TCT가 거의 네트워크 시간으로만 결정된다. Local과 Edge 차이를 보려면 **iter를 바꿔가며 측정**해야 한다 (예: 100 / 10k / 100k / 1M).
3. **`FROM scratch` 이미지**: 셸이 없어서 Fogify의 `command` 액션이나 메트릭 파일 쓰기에 제약이 생긴다. Fogify용은 원본에 이미 있는 alpine 단계(`exportable`)를 사용한다.
4. **유니커널(Nanos) 부분은 제외**: Fogify는 Docker 컨테이너만 다룬다. 이번 실험에서 원본은 "워크로드 출처"로만 쓴다.

## 폴더 구조 (예정)

```
research-docs/                     ← 내 연구 문서 (계획, 결과 기록)
  01-uvc-sha256-plan.md
examples/uvc-sha256/               ← Jupyter에서 examples/로 바로 보임
  upstream/                        ← 원본 소스 그대로 (바이너리 제외) + NOTICE
  server/                          ← Fogify용 엣지 서버 (원본 기반)
  client/                          ← Device 클라이언트 (MODE=local|edge, TCT 기록)
  docker-compose.yaml              ← services + x-fogify (nodes/networks/topology/scenarios)
  uvc-sha256.ipynb                 ← 배포 → 실행 → 수집 → 그래프 → undeploy
```

## 단계별 계획 (단계마다 커밋 1개)

| # | 단계 | 할 일 | 완료 기준 |
|---|---|---|---|
| 0 | 계획 | 브랜치 생성, `research-docs/`, 이 문서 | 이 문서 커밋 |
| 1 | 원본 가져오기 | `upstream/`에 소스만 복사 (`*.go`, `go.mod`, `app.js`, `Dockerfile`, `post.lua`). 출처·커밋·라이선스를 적은 `NOTICE.md` 작성 | 바이너리 없이 커밋 |
| 2 | 원본 단독 실행 | Fogify 없이 `docker build` → `docker run --cpus 1 --memory 128m` → `curl -X POST "localhost:8080/compute?iter=100"` 응답 확인. iter별 응답 시간 대략 측정 | 결과를 문서에 기록 |
| 3 | Fogify용 앱 | **server**: alpine 기반으로 빌드, 처리 시간 로그 추가. **client**: Go로 작성. `MODE=local`이면 같은 해시 함수를 직접 실행, `MODE=edge`면 서버로 POST. 작업마다 `tct_ms`를 CSV로 저장하고 `fogify.metrics.json`도 갱신. 변수: `ITER`, `PAYLOAD_BYTES`, `N_TASKS`, `INTERVAL` | 두 이미지 빌드, 로컬에서 두 모드 모두 동작 |
| 4 | 토폴로지 | compose 작성. **nodes**: device(1코어, 낮은 클럭, 512M), edge(4코어, 2G). **networks**: device↔edge 링크 (기본 RTT 10ms, BW 100Mbps). **topology**: device-local, device-edge, edge-server. **scenarios**: RTT 단계 증가 / BW 단계 감소 / 엣지 `stress` | `fogify.deploy()` 성공 |
| 5 | 노트북 | deploy → Local 실행 → Edge 실행 → 시나리오 → CSV와 metrics 수집 → 그래프 (TCT vs RTT, BW, CPU 부하, iter) → undeploy | 그래프 출력 |
| 6 | 결과 정리 | `research-docs/02-uvc-sha256-results.md`: 설정, 그래프, Local과 Edge가 역전되는 지점 | 문서 커밋 |

## 실험 변수 (초안)

| 변수 | 값 | 조절 방법 |
|---|---|---|
| RTT | 2 / 10 / 50 / 100 / 200 ms | `networks` 지연 (양방향에 절반씩), 시나리오 `update_network` |
| BW | 1 / 10 / 100 Mbps | `networks` bandwidth |
| 엣지 CPU 부하 | 0 / 50 / 90 % | 시나리오 `stress` |
| 연산량 | iter = 100 / 10k / 100k / 1M | 클라이언트 `ITER` |
| payload | 1 KB / 100 KB / 1 MB | 클라이언트 `PAYLOAD_BYTES` (BW 영향이 보이게) |
| 기기 사양 | 1코어, clock_speed로 성능 낮춤 | `nodes` |

각 조건마다 작업 N회 (예: 100회)를 실행하고 **중앙값, p95**로 비교한다.

## 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| clock_speed 제한이 기대만큼 안 걸림 (`.env`의 `CPU_FREQ=2086` 기준으로 환산됨) | 2단계에서 iter별 시간을 재고, Fogify 안에서 다시 재서 비율이 맞는지 확인 |
| tc 지연이 Swarm 오버레이에서 의도대로 적용되는지 | 4단계에서 client 노드에서 `ping` (command 액션)으로 RTT 실측 |
| 노트북 PC 한 대라 엣지와 기기가 같은 CPU를 나눠 씀 | 코어 수를 겹치지 않게 잡고, 다른 무거운 작업은 끈 상태에서 측정 |
| 원본 Go 버전(1.22) 빌드 환경 | 멀티스테이지 Docker 빌드라 호스트에 Go가 없어도 됨 |
