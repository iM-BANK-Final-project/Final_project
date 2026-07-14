export function LoadingState({ message = "데이터를 불러오는 중입니다." }) {
  return (
    <div className="page-state" role="status">
      {message}
    </div>
  );
}

export function EmptyState({ message = "표시할 데이터가 없습니다." }) {
  return <div className="page-state page-empty">{message}</div>;
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="page-state page-error" role="alert">
      <span>{error?.message || "데이터를 불러오지 못했습니다."}</span>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}
