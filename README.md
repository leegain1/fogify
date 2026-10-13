# fogify (연구용 사본)

PC 한 대에서 **로컬 – 엣지 서버 – 클라우드** 환경을 Docker로 흉내 내는 포그 컴퓨팅 에뮬레이터 **Fogify**의 사본입니다.
이 저장소에서는 **로컬 처리 vs 엣지 서버 오프로딩의 TCT(Task Completion Time)**를 실험합니다.

## 1. 이게 뭔가

| 항목 | 내용 |
|---|---|
| 원본 | [UCY-LINC-LAB/fogify](https://github.com/UCY-LINC-LAB/fogify) (Apache-2.0, 키프로스 대학 LInC). 논문에 쓸 때는 [인용](#인용) 필요 |
| Fogify가 하는 일 | 노드마다 CPU·메모리 제한, 노드 사이 네트워크에 지연·대역폭·손실 적용, 실행 중 장애·부하 주입, 지표 수집 |
| 이 사본에서 추가한 것 ① | **최신 Docker / cgroup v2 호환 수정**: cAdvisor v0.53.0, `utils/monitoring.py` cgroup v2 경로, `requirements.txt` 버전 고정, Jupyter 이미지 권한, taxi-demo 이미지 |
| 이 사본에서 추가한 것 ② | **로컬 vs 엣지 서버 오프로딩 실험** (`examples/uvc-sha256/`): 논문 *Unikernels vs. Containers* (arXiv:2509.07891)의 SHA-256 워크로드를 가져와 Fogify 위에서 TCT 비교 |

## 2. 아키텍처

```
 브라우저 ──▶ ui (Jupyter + FogifySDK)  :8888
                 │  deploy / action / metrics (REST)
                 ▼
             controller  :5000 ── 모델 해석 → Docker Swarm으로 노드 배포
                 │
                 ▼
             agent  :5500 ── 노드마다 tc/netem(지연·대역폭), cgroup(CPU·메모리), 모니터링
                 │
                 ▼
   ┌──────────── 에뮬레이션 노드 (Swarm 서비스 컨테이너) ────────────┐
   │  local ──edge-server-net-1──▶ edge-server-1                    │
   │        └─edge-server-net-2──▶ edge-server-2                    │
   └────────────────────────────────────────────────────────────────┘
             cAdvisor  :9090 ── 컨테이너 자원 사용량 수집
```

| 폴더 | 역할 |
|---|---|
| `controller/` | REST API (:5000). 배포, 액션, 모니터링 요청 처리 |
| `agent/` | 노드 제어 API (:5500). 네트워크 규칙 적용, 지표 수집 |
| `connectors/` | 실제 배포 방식 (`SwarmConnector` 사용) |
| `FogifyModel/` | `x-fogify` YAML → 노드·네트워크·액션 객체 |
| `FogifySDK/` | 노트북에서 쓰는 Python SDK |
| `utils/` | 네트워크(tc), 모니터링, Docker 관리 도구 |
| `examples/` | `uvc-sha256/` (이 연구), `taxi-demo/`, `kind-project/` (원본 예제) |
| `research-docs/` | 연구 문서 (개요 + 실험 기록) |
| `docs/`, `docs-code/` | 원본 Fogify 문서 (HTML / 원문 md) |

## 3. 실행 방법

### 준비 (처음 한 번)

```bash
docker swarm init --advertise-addr <호스트 IP>
sudo apt-get install iproute2        # tc
```

저장소 루트에 `.env` 작성 (git에 포함되지 않음):

```ini
MANAGER_NAME=<호스트 이름>          # hostname
MANAGER_IP=<호스트 IP>
HOST_IP=<호스트 IP>
CPU_OVERSUBSCRIPTION_PERCENTAGE=0
RAM_OVERSUBSCRIPTION_PERCENTAGE=0
CPU_FREQ=<호스트 CPU 기준 클럭, MHz>  # 노드 CPU 환산 기준
NAMESPACE_PATH=/proc/
CONNECTOR=SwarmConnector
SNIFFING_ENABLED=false
SNIFFING_PERIOD=15
SNIFFING_PERIODICITY=15
```

### Fogify 켜기

```bash
docker compose -p fogemulator up -d      # 처음 (이미지 빌드 포함)
docker compose -p fogemulator start      # 재부팅 후
docker exec fogemulator-ui-1 jupyter server list   # Jupyter 토큰 확인 (재시작마다 바뀜)
```

### 실험 실행

```bash
docker build -t uvc-sha256:0.1 examples/uvc-sha256/app   # 앱 이미지 (코드 바꿨을 때만)
```

1. http://localhost:8888 → `examples/uvc-sha256/uvc-sha256.ipynb` 열기
2. 위에서부터 실행: **배포 → 실험 A~E → undeploy** (약 12분)
3. 결과는 `examples/uvc-sha256/results/` (CSV + PNG)

노트북을 중간에 멈췄다면 마지막 셀의 `fogify.undeploy()`를 꼭 실행합니다.

## 4. 실험 설정 방법

실험 전체는 **compose 파일 하나**(`examples/uvc-sha256/docker-compose.yaml`)에 적습니다.

```yaml
services:                       # 일반 docker-compose
  local:       {image: uvc-sha256:0.1, command: ["uvc-client", "idle"]}
  edge-server: {image: uvc-sha256:0.1, command: ["uvc-server"]}
x-fogify:
  nodes:                        # 기기 사양
  - {name: local-node, capabilities: {processor: {cores: 1, clock_speed: 1043}, memory: 0.5G}}
  networks:                     # 네트워크 품질 (단위는 Mbit!)
  - {name: edge-server-net-1, bidirectional: {bandwidth: 100Mbit, latency: {delay: 5ms}}}
  topology:                     # 어떤 노드에 어떤 서비스를 어느 네트워크에
  - {label: local, service: local, node: local-node, replicas: 1, networks: [edge-server-net-1]}
  scenarios:                    # 시간순 자동 변경
  - name: rtt-steps
    actions:
    - {time: 30, position: 0, instance_type: edge-server-1, instances: 1,
       action: {type: network, parameters: {network: edge-server-net-1,
         bidirectional: {bandwidth: 100Mbit, latency: {delay: 25ms}}}}}
```

| 항목 | 규칙 |
|---|---|
| CPU | `cores × clock_speed / CPU_FREQ` → Docker CPU 할당량 (소수 첫째 자리 반올림). 예: 1 × 1043 / 2086 = 0.5 CPU |
| RTT | **로컬 쪽 delay + 엣지 서버 쪽 delay**. 기본 5ms + 5ms → 약 10ms |
| 대역폭 | **`Mbit` 사용**. `Mbps`는 MB/s라서 8배가 됨 |
| 시나리오 | `time` = 이전 액션 후 기다리는 초. 실행: `fogify.scenario_execution("rtt-steps")` |

실행 중 조건 변경 (노트북, `FogifySDK`):

```python
fogify.update_network("edge-server-1", "edge-server-net-1",
    {"bidirectional": {"bandwidth": "10Mbit", "latency": {"delay": "50ms"}}})
fogify.stress("edge-server-1", duration=60, cpu=80)   # cpu = 노드 CPU의 %. 이미지에 cpulimit + stress 필요
```

RTT 확인: `docker exec $(docker ps -qf name=fogify_local) ping -c 5 edge-server-1`

TCT 측정 (로컬 노드에서 실행, 작업마다 CSV 한 줄):

```bash
L=$(docker ps -qf name=fogify_local)
docker exec $L uvc-client run -mode local       -iter 1000000 -n 30
docker exec $L uvc-client run -mode edge-server -servers http://edge-server-1:8080 -iter 1000000 -n 30
# CSV: ts_unix_ms,label,mode,target,task,iter,payload_bytes,tct_ms,server_compute_ms,status
```

주요 옵션: `-iter`(연산량), `-payload`(요청 크기 byte), `-n`, `-interval`, `-keepalive`, `-verify`, `-label`.

## 5. 주의사항

| 함정 | 내용 |
|---|---|
| 대역폭 단위 | `Mbps`(MB/s) ≠ `Mbit`. 원본 문서와 예제의 `Mbps`는 실제로 8배 |
| CPU 제한 | 느린 CPU가 아니라 **100ms마다의 할당량**. 몇 ms짜리 작업에는 효과 없음 → iter 100k~3M 사용 |
| 배포 직후 | 네트워크 규칙이 몇 초 늦게 적용됨 → ping으로 RTT 확인 후 측정 |
| 사용자 지표 | `/fogify/metrics`는 현재 수집되지 않음 (agent에 `/var/lib/docker` 미마운트) → **클라이언트 CSV가 주 결과** |
| SDK 함수 이름 | 문서의 `execute_scenario`가 아니라 `scenario_execution` |
| undeploy | 오버레이 네트워크는 남음 (다음 배포 때 재사용, 문제없음) |
| PC 한 대 | 엣지 서버끼리 CPU 격리가 안 됨 → 한 엣지 서버에 건 부하가 다른 엣지 서버에도 번짐 |

## 6. 현재 결과 한눈에 (iter 1M, n=30, 중앙값)

- **연산량**: 작은 작업(100k)은 로컬 처리(5.6ms), 큰 작업은 엣지 서버 오프로딩(65.8 vs 115.8ms)이 유리
- **RTT**: 엣지 서버 TCT ≈ 계산 약 58ms + RTT → **RTT 약 55~90ms에서 로컬 처리와 역전**
- **대역폭** (256KB): **10Mbit 이하면 로컬 처리가 유리** (292ms vs 113ms)
- **로컬 처리 분포가 두 갈래** (약 115ms / 약 170ms, CPU 할당량 주기 때문) → 중앙값보다 분포로 비교해야 함
- 상세: [research-docs/uvc-sha256.md](research-docs/uvc-sha256.md#5-실험-결과-노트북)

## 7. 문서

| 문서 | 내용 |
|---|---|
| [research-docs/README.md](research-docs/README.md) | 연구 개요, 용어, 진행 상황, 핵심 발견 |
| [research-docs/uvc-sha256.md](research-docs/uvc-sha256.md) | SHA-256 실험 상세 기록 (출처, 설계, 측정, 결과, 다음 할 일) |
| [examples/uvc-sha256/upstream/NOTICE.md](examples/uvc-sha256/upstream/NOTICE.md) | 논문 코드 출처와 라이선스 |
| https://ucy-linc-lab.github.io/fogify/ | 원본 Fogify 문서 |

용어: **로컬** = 작업을 만드는 기기, **엣지 서버** = 로컬과 클라우드 사이의 서버, **TCT** = 작업 시작부터 결과 수신까지 시간.

## 인용

Fogify를 연구에 쓰면 원본 논문을 인용합니다.

```bibtex
@inproceedings{Symeonides2020,
  author    = {Moysis, Symeonides and Zacharias, Georgiou and Demetris, Trihinas and George, Pallis and Marios D., Dikaiakos},
  title     = {Fogify: A Fog Computing Emulation Framework},
  year      = {2020},
  booktitle = {Proceedings of the 5th ACM/IEEE Symposium on Edge Computing (SEC '20)}
}
```
