# 연구 노트: 로컬 처리 vs 엣지 서버 오프로딩 (Fogify)

`docs/`, `docs-code/`는 Fogify 원본 문서다. **내 문서는 이 폴더의 두 파일뿐이다.**

| 파일 | 내용 |
|---|---|
| `README.md` (이 문서) | 개요, 용어, 진행 상황, 실행 방법, 핵심 발견 |
| [`uvc-sha256.md`](uvc-sha256.md) | SHA-256 실험 상세 기록: 원본 출처, 앱과 토폴로지 설계, 측정값, 결과 그래프 |

## 용어

| 용어 | 뜻 | 코드/라벨 |
|---|---|---|
| **로컬** | 작업을 만들어내는 기기 자신 | `local` |
| **엣지 서버** | 로컬 근처, 로컬과 클라우드 사이에 있는 서버 | `edge-server-1`, `edge-server-2` |
| **TCT** | Task Completion Time. 로컬에서 작업 시작부터 결과 수신까지 | `tct_ms` |

※ "엣지"라는 말만 단독으로 쓰지 않는다.

## 진행 상황 (브랜치 `exp/uvc-sha256`)

| # | 단계 | 상태 |
|---|---|---|
| 1 | 원본 코드 가져오기 (`examples/uvc-sha256/upstream/`) | ✅ |
| 2 | 원본만 단독 실행해서 iter별 계산 시간 측정 | ✅ |
| 3 | Fogify용 앱 (`uvc-server`, `uvc-client`) | ✅ |
| 4 | 토폴로지 배포 확인 (로컬 1 + 엣지 서버 2) | ✅ |
| 5 | 노트북으로 실험 A~E 실행 | ✅ |
| 6 | 대역폭 문제 확인, 반복 측정, 연구 확장 | 다음 → [uvc-sha256.md 6절](uvc-sha256.md#6-다음-할-일) |

## 실행 방법

```bash
# 0) Fogify 켜기 (PC 재부팅 후) — Jupyter 토큰은 재시작할 때마다 바뀜
docker compose -p fogemulator start
docker exec fogemulator-ui-1 jupyter server list

# 1) 앱 이미지 (코드를 바꿨을 때만)
docker build -t uvc-sha256:0.1 examples/uvc-sha256/app
```

2) Jupyter(http://localhost:8888)에서 `examples/uvc-sha256/uvc-sha256.ipynb`를 열고 위에서부터 실행한다. 배포 → 실험 A~E → undeploy까지 약 10분 걸린다. 결과는 `examples/uvc-sha256/results/`에 저장된다.

## 파일 위치

| 경로 | 내용 |
|---|---|
| `examples/uvc-sha256/upstream/` | 원본 소스 (수정 없음) + `NOTICE.md` (출처, 라이선스) |
| `examples/uvc-sha256/app/` | Fogify용 앱. 이미지 하나에 `uvc-server`(엣지 서버)와 `uvc-client`(로컬) |
| `examples/uvc-sha256/docker-compose.yaml` | 토폴로지 + 시나리오 3개 (`rtt-steps`, `bw-steps`, `edge-server-1-stress`) |
| `examples/uvc-sha256/uvc-sha256.ipynb` | 실험 노트북 |
| `examples/uvc-sha256/results/` | 실험 CSV와 그래프 |

## 핵심 발견 (빠른 참고)

| 항목 | 내용 |
|---|---|
| 논문의 iter=100 | 계산이 거의 0 → 측정값이 HTTP 시간뿐. **iter 100k~3M** 사용 |
| CPU 제한 | 느린 CPU가 아니라 **100ms마다의 할당량**이다. 짧은 작업(수 ms)에는 효과가 없다 |
| Fogify CPU 계산 | `cores × clock_speed / CPU_FREQ(2086)` → Docker `NanoCpus`. 소수 첫째 자리로 반올림 |
| RTT | **로컬 쪽 delay + 엣지 서버 쪽 delay** (5+5 → 약 10ms). 엣지 서버마다 따로 조절 가능 |
| stress 액션 | 컨테이너 안에서 `cpulimit` + `stress` 실행 → 이미지에 설치함. `cpu`는 노드 CPU의 % |
| 사용자 지표 | `/fogify/metrics`는 현재 수집되지 않음 → **클라이언트 CSV가 주 결과** |
| Fogify 문서와 실제 코드 차이 | 지표 파일은 `fogify.metrics.json`이 아니라 `/fogify/metrics`. 시나리오 함수는 `execute_scenario`가 아니라 `scenario_execution`. `time`은 이전 액션 후 기다리는 초 |
| 실험 결과 요약 | → [uvc-sha256.md 결과](uvc-sha256.md#5-실험-결과-노트북) |
