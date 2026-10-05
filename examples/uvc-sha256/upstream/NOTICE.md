# NOTICE

이 폴더의 파일은 아래 저장소에서 **수정 없이** 복사했다.

| 항목 | 내용 |
|---|---|
| 저장소 | https://github.com/haidinhtuan/Unikernel-vs-Container |
| 커밋 | `4e00774` (2026-04-02) |
| 라이선스 | Apache License 2.0 (`LICENSE` 참고) |
| 논문 | H. Dinh-Tuan, *Unikernels vs. Containers: A Runtime-Level Performance Comparison for Resource-Constrained Edge Workloads*, IEEE (arXiv:2509.07891) |

## 가져온 것

| 경로 | 설명 |
|---|---|
| `go-compute-app/` | `POST /compute?iter=N`: body를 SHA-256으로 N번 반복 해시 (:8080). 기본값 `iter=20000` |
| `go-http-app/` | `GET /hello`: 바로 응답 (I/O 워크로드) |
| `node-compute-app/`, `node-http-app/` | 위와 같은 기능의 Node.js 버전. `config.json`은 Nanos(ops)용 설정 |
| `post.lua` | `wrk` 부하 도구용 POST 스크립트 (`payload.dat`를 body로 보냄) |

## 가져오지 않은 것

- 미리 빌드된 바이너리 (`main`, `go-compute-app`, `myapp` 등, 약 130MB) → `Dockerfile`로 다시 빌드한다
- 백업 파일 (`*.bk`), 기동 시간 측정 스크립트 (`measure_*.sh`), `generate_system_report.sh`
- 논문 그림 (`docs/figures/`)

이 폴더는 원본 기록용으로 그대로 두고, Fogify용으로 고친 코드는 `../server/`, `../client/`에 따로 둔다.
