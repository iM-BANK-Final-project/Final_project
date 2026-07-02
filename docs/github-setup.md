# GitHub Organization Setup

## 1. Organization 생성

GitHub에서 새 Organization을 만들고 팀원을 초대합니다.

권장 설정:

- Organization name: 팀명 또는 프로젝트명
- Repository visibility: 프로젝트 정책에 따라 Private 권장
- Member role: 기본은 Member, 저장소별 권한 부여

## 2. Repository 생성

Organization 안에 새 저장소를 만듭니다.

권장 설정:

- Repository name: `final-project` 또는 서비스명이 정해진 뒤 확정
- Visibility: Private
- Initialize with README: 로컬 README가 있으므로 체크하지 않음

## 3. Local Repository 연결

```bash
git remote add origin https://github.com/<organization>/<repository>.git
git push -u origin main
```

## 4. Branch Protection

GitHub 저장소의 `Settings > Branches`에서 `main` 보호 규칙을 추가합니다.

권장 규칙:

- Require a pull request before merging
- Require approvals
- Require status checks to pass before merging
- Require conversation resolution before merging
- Do not allow force pushes

## 5. Recommended Labels

GitHub Issues의 Labels에서 README의 라벨 목록을 추가합니다.

초기 라벨:

- `planning`
- `data`
- `backend`
- `frontend`
- `ml`
- `docs`
- `bug`
- `security`
- `priority-high`

