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

async function errorFromResponse(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return new ApiError(
    body?.detail || response.statusText || "요청을 처리하지 못했습니다.",
    response.status,
    body
  );
}

function safeFilename(value, fallback = "ai_strategy_report.pdf") {
  const sanitized = (value || "").replace(/[\\/\0\r\n]/g, "_").trim();
  return sanitized || fallback;
}

function responseFilename(response) {
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return safeFilename(decodeURIComponent(encoded));
    } catch {
      return safeFilename(encoded);
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return safeFilename(plain);
}

export async function apiGet(path, params, signal) {
  const response = await fetch(buildUrl(path, params), { signal });

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return response.json();
}

export async function apiPost(path, body = {}, params = {}, signal) {
  const response = await fetch(buildUrl(path, params), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal
  });

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return response.json();
}

export async function apiPostBlob(path, body = {}, params = {}, signal) {
  const response = await fetch(buildUrl(path, params), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal
  });

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return {
    blob: await response.blob(),
    filename: responseFilename(response)
  };
}
