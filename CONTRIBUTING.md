# Contributing Guide

## Commit Message

다음 형식을 권장합니다.

```text
<type>: <short summary>
```

사용 가능한 `type` 예시는 다음과 같습니다.

- `feat`: 기능 추가
- `fix`: 버그 수정
- `docs`: 문서 수정
- `refactor`: 동작 변경 없는 구조 개선
- `test`: 테스트 추가 또는 수정
- `chore`: 설정, 빌드, 기타 작업

예시:

```text
feat: add corporate customer segmentation API
docs: add data handling policy
```

## Pull Request Checklist

- 관련 이슈를 연결했습니다.
- 변경 목적과 핵심 내용을 설명했습니다.
- 직접 실행한 검증 방법을 적었습니다.
- 민감정보 또는 원본 고객 식별 데이터가 포함되지 않았습니다.
- 필요한 문서를 업데이트했습니다.

## Data Handling

- 원본 데이터는 저장소에 커밋하지 않습니다.
- 샘플 데이터가 필요하면 익명화된 소량 데이터만 사용합니다.
- 고객명, 사업자번호, 연락처, 계좌, 계약번호 등 직접 식별자는 커밋 전에 제거합니다.
- 분석 결과를 공유할 때 재식별 가능성이 있는 조합을 피합니다.

