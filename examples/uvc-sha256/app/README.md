# uvc-sha256 app

원본 `upstream/go-compute-app`의 SHA-256 워크로드를 Fogify 실험용으로 다시 구성한 앱이다.
이미지 하나(`uvc-sha256:0.1`)에 두 개의 바이너리가 들어 있다.

| 바이너리 | 실행 위치 | 역할 |
|---|---|---|
| `uvc-server` (기본 CMD) | 엣지 서버 노드 | `POST /compute?iter=N` (원본과 같은 API) + 응답 헤더 `X-Compute-Us`(서버 계산 시간), `X-Server`(호스트명). `GET /hello` |
| `uvc-client` | 로컬 노드 | `idle`: 컨테이너를 켜둔 채 대기. `run`: 작업을 N번 실행하고 작업마다 CSV 한 줄 출력 |

로컬 처리와 엣지 서버 오프로딩은 같은 함수(`internal/work.Hash`)를 쓴다. 그래서 두 방식의 계산량은 정확히 같다.

## 빌드

```bash
docker build -t uvc-sha256:0.1 examples/uvc-sha256/app
```

## 클라이언트 사용법

```bash
uvc-client run -mode local       -iter 1000000 -n 50 -label base
uvc-client run -mode edge-server -servers http://edge-server-1:8080,http://edge-server-2:8080 \
               -iter 1000000 -n 50 -label base
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `-mode` | `local` | `local` 또는 `edge-server` |
| `-servers` | `http://edge-server-1:8080` | 엣지 서버 주소 목록 (쉼표로 구분, 순서대로 돌아가며 보냄) |
| `-iter` | 100000 | 작업당 SHA-256 반복 횟수 |
| `-payload` | 1024 | 요청 body 크기 (byte). 엣지 서버 오프로딩에서 BW 영향이 보이게 할 때 키움 |
| `-n` / `-warmup` | 20 / 1 | 기록할 작업 수 / 기록 전에 버리는 작업 수 |
| `-interval` | 0 | 작업 사이 대기 시간 (예: `100ms`) |
| `-keepalive` | true | false면 작업마다 TCP 연결을 새로 맺음 (RTT가 1번 더 붙음) |
| `-verify` | false | 엣지 서버가 돌려준 해시가 맞는지 검사. **TCT 측정이 끝난 뒤에** 검사함 |
| `-label` | "" | 실험 조건 태그 (CSV의 모든 줄에 기록) |

### CSV 컬럼

`ts_unix_ms, label, mode, target, task, iter, payload_bytes, tct_ms, server_compute_ms, status`

- `tct_ms`: 로컬에서 잰 작업 완료 시간
- `server_compute_ms`: 엣지 서버가 계산에 쓴 시간 (로컬 처리에서는 빈 칸). `tct_ms - server_compute_ms` = 네트워크 + 대기 시간
- `status`: `ok`, `error:...`, `http:<코드>`, `hash-mismatch`

또 작업마다 `/fogify/metrics`에 `tct_us_last`, `tct_us_avg`, `tasks_done`, `mode_edge_server`를 정수로 씀 (Fogify 모니터링용).

## Fogify 없이 동작 확인 (2026-10-05)

로컬 1개(`--cpus 0.5`) + 엣지 서버 2개(`--cpus 2`), 같은 Docker 네트워크, 지연을 추가하지 않은 상태. n=10, 중앙값:

| iter | 로컬 처리 | 엣지 서버 오프로딩 |
|---:|---:|---:|
| 100 | 0.007 ms | 0.158 ms |
| 100,000 | 5.78 ms | 7.39 ms |
| 1,000,000 | 113.5 ms | 55.6 ms |
| 3,000,000 | 397.2 ms | 164.9 ms |

- 엣지 서버 2대에 순서대로 요청이 가고, `-verify`로 해시가 일치하는 것을 확인했다. 잘못된 주소나 모드를 넣으면 오류가 표시된다.
- iter=100k에서 로컬이 더 빠른 이유: `--cpus 0.5`는 100ms마다 50ms만 CPU를 쓰게 하는 **할당량 제한**이다. 그래서 몇 ms짜리 작업은 제한에 걸리기 전에 끝난다. 작업이 길어지면 로컬은 약 2배 느려진다 (1M: 113 vs 56ms).
