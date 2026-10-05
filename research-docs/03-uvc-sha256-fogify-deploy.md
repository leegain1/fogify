# 03. Fogify 배포 확인 (로컬 1 + 엣지 서버 2)

- 브랜치: `exp/uvc-sha256` / 계획: [01-uvc-sha256-plan.md](01-uvc-sha256-plan.md) 4단계
- 측정일: 2026-10-05
- 파일: `examples/uvc-sha256/docker-compose.yaml`, 이미지 `uvc-sha256:0.1`

## 토폴로지

```
            edge-server-net-1 (5ms, 100Mbps)
  local ─────────────────────────────────────▶ edge-server-1
 (0.5 CPU,  edge-server-net-2 (5ms, 100Mbps)   (2.0 CPU, 1G)
  512M)  ─────────────────────────────────────▶ edge-server-2
                                                (2.0 CPU, 1G)
```

| label | 서비스 | 노드 사양 (x-fogify) | 실제 Docker 제한 |
|---|---|---|---|
| `local` | `uvc-client idle` | 1코어 × 1043MHz, 0.5G | `NanoCpus=0.5`, 512MiB ✅ |
| `edge-server-1` | `uvc-server` | 2코어 × 2086MHz, 1G | `NanoCpus=2.0`, 1GiB ✅ |
| `edge-server-2` | `uvc-server` | 2코어 × 2086MHz, 1G | `NanoCpus=2.0`, 1GiB ✅ |

## 실행 방법

```python
# Jupyter (examples/uvc-sha256/) 에서
from FogifySDK import FogifySDK
fogify = FogifySDK("http://controller:5000", "docker-compose.yaml")
fogify.deploy()
```
```bash
# 로컬 노드에서 작업 실행 (터미널 또는 노트북의 !docker exec)
L=$(docker ps -qf name=fogify_local)
docker exec $L uvc-client run -mode local -iter 1000000 -n 10
docker exec $L uvc-client run -mode edge-server \
  -servers http://edge-server-1:8080,http://edge-server-2:8080 -iter 1000000 -n 10
```
```python
fogify.undeploy()
```

## 확인 결과

### 1. 배포와 이름 찾기

`deploy()`는 약 10초 걸린다. 로컬에서 `edge-server-1`, `edge-server-2`라는 이름으로 바로 접속된다 (Swarm DNS).

### 2. RTT 규칙 (중요)

| 설정 (local 쪽 / 엣지 서버 쪽 delay) | ping RTT 실측 (평균) |
|---|---|
| 5ms / 5ms (기본) | 11.0 ms (최소 10.1) |
| 5ms / **50ms** (`update_network`를 edge-server-1에 적용) | 55.5 ms |
| edge-server-2 (변경 안 함) | 11.3 ms ← 영향 없음 ✅ |

→ **RTT ≈ 로컬 쪽 delay + 엣지 서버 쪽 delay**. 원하는 RTT가 R이면, 로컬 쪽을 5ms로 고정하고 엣지 서버 쪽을 `R − 5ms`로 설정한다.
문서의 "양쪽에 절반씩"이라는 설명과 같은 뜻이다. 네트워크마다 따로 적용되므로 **엣지 서버별로 RTT를 다르게** 줄 수 있다.

### 3. TCT 첫 측정 (iter = 1M, n = 10, 중앙값)

| 방식 | TCT | 엣지 서버 계산 시간 | 네트워크 + 기타 |
|---|---:|---:|---:|
| 로컬 처리 (0.5 CPU) | 111.5 ms | – | – |
| 엣지 서버 오프로딩 (RTT ≈ 11ms) | 68.7 ms | 57.9 ms | ≈ 10.8 ms |
| 엣지 서버 오프로딩, iter = 100 | 11.1 ms | ≈ 0 | ≈ RTT |

→ TCT = 엣지 서버 계산 시간 + RTT로 깔끔하게 나뉜다. `-verify`로 해시가 일치하는 것도 확인했다.

### 4. stress 액션 (엣지 서버 CPU 부하)

`fogify.stress('edge-server-1', duration=30, cpu=80)`

| | 엣지 서버 계산 시간 | TCT |
|---|---:|---:|
| 부하 없음 | 56.3 ms | 67.4 ms |
| 부하 80% | 83.6 ms | 94.3 ms |

- Fogify는 컨테이너 **안에서** `cpulimit --limit 160 -i -- stress --cpu 2 --timeout 30`을 실행한다. 그래서 이미지에 `cpulimit`과 `stress`가 있어야 한다. 원본 alpine 이미지에는 없어서 `cpulimit`과 `stress-ng`를 설치하고, `stress`라는 이름으로 연결했다.
- `cpu` 값은 **노드 CPU의 퍼센트**다 (`limit = cpus × cpu`). 처음에 시나리오에 `cpu: 2`라고 적었는데, 이러면 4%가 되므로 `80`으로 고쳤다.

### 5. Fogify 모니터링

- 기본 지표(`cpu_util`, `memory`, 네트워크별 rx/tx)는 `get_metrics_from('local.1')`로 받아진다.
- **사용자 지표(`/fogify/metrics`)는 수집되지 않는다.** agent가 `docker inspect`의 MergedDir(호스트 경로)를 읽으려고 하는데, agent 컨테이너에는 `/var/lib/docker`가 마운트되어 있지 않다. 고치려면 Fogify `docker-compose.yaml`의 agent에 `/var/lib/docker`를 마운트해야 한다. 지금은 **클라이언트 CSV를 주 결과로 쓰기로** 하고 그대로 둔다.

### 6. 기타

- `undeploy()` 후에도 오버레이 네트워크(`edge-server-net-1`, `-2`)는 남는다. 다음 배포 때 다시 쓰이므로 문제없다. 예전 taxi-demo가 남긴 `internet`, `edge-net-1`, `edge-net-2`는 컨테이너가 연결되어 있지 않은 것을 확인하고 지웠다.
- SDK의 시나리오 실행 함수 이름은 문서에 나온 `execute_scenario`가 아니라 **`scenario_execution(name)`**이다. 각 액션의 `time`은 **이전 액션 후 기다리는 초**다.
- 시나리오 3개(`rtt-steps`, `bw-steps`, `edge-server-1-stress`)는 compose에 정의만 해 두었다. 같은 동작을 하는 개별 액션(`update_network`, `stress`)으로 효과를 확인했고, 시나리오 전체 실행은 5단계 노트북에서 한다.
