# Concurrently 통합 개발 실행기 설계

## 목표

프로젝트 루트에서 `npm run dev` 한 번으로 FastAPI 백엔드와 Vite 프론트엔드를 동시에 실행한다.

## 실행 계약

- 사용자는 먼저 프로젝트에 필요한 Python 환경을 활성화한다.
- 루트 `npm run dev`는 현재 활성화된 `python`으로 FastAPI를 `127.0.0.1:8000`에서 실행한다.
- 같은 명령이 프론트엔드 패키지의 기존 `dev` 스크립트를 호출해 Vite를 `127.0.0.1:5173`에서 실행한다.
- 로그에는 `BACKEND`, `FRONTEND` 이름을 표시한다.
- `Ctrl+C` 또는 한 프로세스의 실패 시 다른 프로세스도 종료한다.
- 서비스 DB 생성은 통합 실행 명령에 포함하지 않는다. 기존 준비 명령을 명시적으로 실행한다.

## 구현

루트 `package.json`에 다음 역할을 분리한다.

- `dev`: `concurrently`로 두 하위 명령을 실행한다.
- `dev:backend`: `python -m uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload`
- `dev:frontend`: 기존 프론트엔드 패키지의 `dev` 스크립트를 호출한다.

`concurrently`는 루트 개발 의존성으로 잠그고 `package-lock.json`을 함께 관리한다. README에는 최초 설치, Python 환경 활성화, DB 준비, 통합 실행 순서를 기록한다.

## 오류 처리

- Python 환경에 백엔드 의존성이 없으면 `BACKEND` 로그에서 즉시 실패 원인을 확인할 수 있다.
- 루트 또는 프론트엔드 Node 의존성이 없으면 `npm install` 안내를 따른다.
- 포트 충돌은 해당 프로세스의 오류로 노출되고 `concurrently -k`가 나머지 프로세스도 정리한다.

## 검증

- 구조 테스트에서 루트 스크립트가 정확한 백엔드·프론트엔드 명령과 종료 옵션을 포함하는지 확인한다.
- 프론트엔드 테스트와 빌드를 실행한다.
- 통합 실행 명령을 짧게 기동해 백엔드 `/api/health`와 프론트엔드 응답을 확인하고 두 프로세스가 함께 종료되는지 확인한다.
