# 02. 원본 SHA-256 서버 단독 실행 (Fogify 없이)

- 브랜치: `exp/uvc-sha256` / 계획: [01-uvc-sha256-plan.md](01-uvc-sha256-plan.md) 2단계
- 측정일: 2026-10-05

## 목적

원본 `go-compute-app`이 수정 없이 빌드되고 동작하는지 확인한다. 그리고 `iter`에 따라 계산 시간이 얼마나 되는지 감을 잡는다.
이 값이 이후 Fogify 실험에서 **로컬 vs 엣지 서버**를 비교할 때 `iter` 범위를 정하는 기준이 된다.

## 환경

| 항목 | 값 |
|---|---|
| CPU | Intel i5-1240P (16 스레드), 노트북 |
| OS / 커널 | Ubuntu, Linux 6.8.0 |
| Docker | 29.8.2 |
| 컨테이너 제한 | `--cpus 1 --memory 128m` (논문의 resource-constrained 조건과 같은 CPU 개수) |
| 요청 | `POST /compute?iter=N`, body = 랜덤 1KB, 같은 호스트에서 `curl` 20회 |

## 실행 방법

```bash
cd examples/uvc-sha256/upstream/go-compute-app
docker build -t uvc-go-compute:upstream .
docker run -d --name uvc-test --cpus 1 --memory 128m -p 18080:8080 uvc-go-compute:upstream
head -c 1024 /dev/urandom > p1k.dat
curl -s -o /dev/null -w '%{time_total}\n' -X POST --data-binary @p1k.dat "localhost:18080/compute?iter=100000"
docker rm -f uvc-test
```

## 결과

빌드 문제 없음. 응답은 64자리 hex 해시로 정상이다. 메모리는 약 2MB만 사용한다.

| iter | 중앙값 (ms) | 최소 | 최대 |
|---:|---:|---:|---:|
| 100 | 0.58 | 0.33 | 0.86 |
| 10,000 | 1.42 | 1.21 | 2.31 |
| 100,000 | 7.33 | 6.38 | 10.04 |
| 1,000,000 | 58.58 | 56.94 | 67.82 |

※ `curl`의 전체 시간이라 루프백 HTTP 비용(약 0.3~0.5ms)이 포함되어 있다.

## 해석

- **iter=100 (논문 값)은 계산이 거의 0이다.** 측정값은 사실상 HTTP 오버헤드다. RTT가 몇 ms만 되어도 계산 시간은 묻혀 버린다.
- 1코어 기준 **SHA-256 1회당 약 0.06µs**다. iter와 시간이 거의 비례한다 (100k → 7ms, 1M → 59ms).
- 따라서 로컬 vs 엣지 서버 비교에서 쓸 만한 범위는 **iter = 100k ~ 수백만**이다.
  - 로컬은 Fogify에서 CPU를 더 낮게 제한한다 (예: 1코어의 일부). 그러면 같은 iter에서도 계산 시간이 몇 배 늘어난다.
  - 엣지 서버는 계산은 빠르지만 RTT와 전송 시간이 더해진다.
  - 이 둘이 교차하는 지점을 찾는 것이 실험의 핵심이다.

## 다음 단계에 반영할 것

- 클라이언트 기본값은 `ITER=100000`으로 하고, 실험에서는 `100 / 100k / 1M / 3M` 정도로 바꿔가며 측정한다.
- 서버가 응답 헤더로 **서버 계산 시간**을 돌려주게 한다. 그러면 TCT를 (네트워크 + 대기) 시간과 계산 시간으로 나눠 볼 수 있다.
