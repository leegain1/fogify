# NOTICE

이 폴더의 코드는 아래 저장소에서 **수정 없이** 복사했다.

| 항목 | 내용 |
|---|---|
| 저장소 | https://github.com/ImanRHT/QECO |
| 커밋 | `9221263` (2025-04-05) |
| 라이선스 | MIT License (`LICENSE` 참고) |
| 논문 | I. Rahmati et al., *QECO: A QoE-Oriented Computation Offloading Algorithm based on Deep Reinforcement Learning for Mobile Edge Computing* |

## 가져온 것

| 경로 | 설명 |
|---|---|
| `Config.py` | 시스템 설정 (UE 20대, 엣지 서버 2대, 1000 에피소드, 0.1초 타임슬롯) |
| `MEC_Env.py` | 시뮬레이터 환경 (큐 기반) |
| `D3QN.py` | D3QN + LSTM 모델 (TensorFlow 1.x API, `tf.compat.v1`) |
| `main.py` | 학습 루프와 QoE 보상 |
| `README.md`, `requirements.txt`, `assets/` | 원본 설명과 그림 |
| `reference_20UE_2EN_RandomMode/` | 원본의 `TrainedModel_20UE_2EN_RandomMode/`에서 학습 기록(txt)과 그래프만 가져옴. 파일 이름의 ` 06.16.34` 접미사만 지움 |

## 가져오지 않은 것

- 학습된 체크포인트 (`TrainedModel_*/800/`, 약 35MB)
- `.github/`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.DS_Store`

이 폴더는 원본 기록용으로 그대로 두고, 테스트베드용으로 고친 코드는 `../qeco_sim/`에 따로 둔다.
