# 프로젝트 Legacy 정리 설계

## 목적

현재 서비스 실행과 최종 모델 재현에 필요한 파일은 기존 경로에 유지하고, 명확히 사용되지 않는 과거 코드·문서·산출물을 루트 `legacy/`로 격리한다. 정리 후에도 서비스 DB 재생성, 백엔드 실행, 프론트 실행, 최종 모델 후보 비교가 가능해야 한다.

## 보존 기준

다음 중 하나라도 만족하면 활성 영역에 유지한다.

- README의 서비스 실행 명령에서 직접 사용한다.
- 백엔드 또는 프론트 런타임에서 import한다.
- 활성 테스트가 검증한다.
- 최종 모델·Y·FISIM·CLV의 source of truth다.
- 최종 모델 재현 또는 새 후보 모델과의 비교에 필요하다.
- GitHub 협업, 환경 구성, 보안 또는 비밀 관리에 필요하다.

## 활성 영역에 유지할 항목

- `src/backend/`의 서비스 코드 전체
- `src/frontend/rm-insight-copilot/`의 현재 프론트 코드·테스트·자산
- `src/models/web_202512_m12_final_model.ipynb`
- `src/수익성F(y선정포함).ipynb`
- 적격 3,341개 운영 점수와 2025-07~12 위험 추세 CSV
- 원천 패널, FTP, 은행 금리, 현재 SQLite, `clv_202512.csv`
- `outputs/수익성F_models/`와 현재 최종 노트북이 생성·소비하는 모델 산출물
- 현재 서비스·CLV·AI 보고서·노트북 계약 테스트
- `README.md`, `AGENTS.md`, `financial_dormancy.md`, `src/models/model.md`
- 최종 통합 설계와 `y_setting_pipeline.md`
- GitHub 설정, `environment.yml`, 보안·기여 문서, `.env`

## Legacy 이동 기준

다음 항목은 `legacy/` 아래에서 기존 상대 구조를 최대한 유지한다.

- 초기 EDA와 이전 수익성 노트북
- 과거 `financial_dormancy`, `persistent_weakening`, 세그먼트 ablation Python 파이프라인
- 위 과거 모듈만 검증하는 테스트
- 구현 완료 후 런타임에서 참조되지 않는 계획·설계·SDD 보고서
- 과거 모델·라벨·해석·프레젠테이션 출력
- 현재 수식에서 더 이상 생성하지 않는 forecast 기반 FISIM 출력
- 이전 서비스 입력 `profitability.csv`, `segment_panel.csv`
- 샘플 PDF와 전체 3,372개 점수 CSV
- 프론트에서 import되지 않는 `MiniTrendChart.jsx`

## 삭제 기준

원본 또는 코드에서 즉시 재생성할 수 있고 보존 가치가 없는 항목만 삭제한다.

- `.DS_Store`
- `.pytest_cache/`, 모든 `__pycache__/`
- 프론트 `dist/`
- 빈 `tmp/`, `tools/`
- 비어 있지 않은 디렉터리의 불필요한 `.gitkeep`
- 임시 review diff

`node_modules/`와 `.env`는 삭제하지 않는다.

## 테스트 격리

루트 `pytest.ini`에 `testpaths = tests`를 설정하여 `legacy/tests/`를 기본 테스트 수집에서 제외한다. 활성 테스트는 과거 모듈 import를 포함하지 않아야 한다.

## 문서와 추적성

- `legacy/README.md`에 이동 범주, 이유, 활성 source-of-truth를 기록한다.
- 활성 문서에서 이동된 경로를 현재 경로처럼 소개하지 않는다.
- Git 추적 파일은 `git mv`와 동등한 rename 이력으로 남긴다.
- 무시된 대용량 출력은 같은 파일시스템 안에서 이동하고 Git에는 추가하지 않는다.

## 검증 계약

정리 후 다음 조건을 모두 만족해야 한다.

1. `python -m src.backend.prepare_service_database` 성공
2. 고객 3,341개, SHAP 33,410행, 위험 추세 6행
3. 활성 Python 테스트 전체 통과
4. 프론트 테스트 전체 통과
5. Vite production build 성공
6. 백엔드 앱 import 및 health endpoint 정상
7. Git 추적 파일에 깨진 활성 경로 참조가 없음

검증 실패 시 정리 작업을 완료로 간주하지 않으며, 필요한 파일을 활성 위치로 복원하거나 참조를 수정한다.
