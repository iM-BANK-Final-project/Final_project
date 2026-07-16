const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function buildUrl(path, params = {}) {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });

  const queryString = query.toString();
  return `${API_BASE_URL}${path}${queryString ? `?${queryString}` : ""}`;
}

export async function apiGet(path, params, signal) {
  const response = await fetch(buildUrl(path, params), { signal });
  const body = await response.json();

  if (!response.ok) {
    throw new ApiError(
      body?.detail || response.statusText || "요청을 처리하지 못했습니다.",
      response.status,
      body
    );
  }

  return body;
}
