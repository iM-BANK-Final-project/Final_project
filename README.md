<<<<<<< HEAD
# Final Project

법인고객의 36개월 데이터를 활용해 웹서비스를 기획, 개발, 검증하는 최종 프로젝트 저장소입니다.

## Project Scope

- 데이터: 법인고객 관련 36개월 기간 데이터
- 목표: 데이터 기반 문제를 정의하고, 사용자가 실제로 활용할 수 있는 웹서비스 구현
- 현재 상태: 구체적인 서비스 주제 탐색 및 협업 환경 구축 단계

## Collaboration

### Branch Strategy

- `main`: 배포 가능하거나 안정적인 코드만 유지합니다.
- `dev`: 기능 통합 및 QA용 브랜치로 사용합니다.
- `feature/<issue-number>-<short-name>`: 기능 개발 브랜치입니다.
- `fix/<issue-number>-<short-name>`: 버그 수정 브랜치입니다.
- `docs/<issue-number>-<short-name>`: 문서 작업 브랜치입니다.

### Issue Flow

1. GitHub Issue를 생성해 작업 목적과 완료 조건을 정리합니다.
2. 담당자와 라벨을 지정합니다.
3. 브랜치를 생성하고 작업합니다.
4. PR에서 이슈 번호를 연결합니다. 예: `Closes #12`

### Pull Request Rules

- PR은 가능한 한 작은 단위로 만듭니다.
- 데이터 처리, 모델링, 화면 변경은 검증 방법을 반드시 적습니다.
- 민감정보, 원본 고객 식별자, 비식별화되지 않은 데이터는 커밋하지 않습니다.
- 리뷰 승인 후 병합합니다.

## Suggested Labels

- `planning`: 기획 및 주제 탐색
- `data`: 데이터 수집, 정제, 분석
- `backend`: API, 서버, DB
- `frontend`: UI, 화면, 사용자 경험
- `ml`: 모델링, 예측, 추천, 군집화
- `docs`: 문서
- `bug`: 버그
- `security`: 보안, 개인정보, 접근 권한
- `priority-high`: 우선순위 높음

## Repository Setup

GitHub Organization과 원격 저장소가 준비되면 아래처럼 연결합니다.

```bash
git remote add origin https://github.com/<organization>/<repository>.git
git push -u origin main
```

=======
# Final_project
IM Digital banker Academy FInal project
>>>>>>> 7449151b96095b5a93167a8e90a17642beeb490d
