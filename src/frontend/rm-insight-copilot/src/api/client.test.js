import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("omits undefined, null, and empty-string query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/api/customers", {
      search: "",
      segment: undefined,
      region: null
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/customers", {
      signal: undefined
    });
  });

  it("URL-encodes Korean query parameter values", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/api/customers", { region: "서울 특별시" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/customers?region=%EC%84%9C%EC%9A%B8+%ED%8A%B9%EB%B3%84%EC%8B%9C",
      { signal: undefined }
    );
  });

  it("converts non-2xx JSON responses into ApiError instances", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "고객을 찾을 수 없습니다." }), {
          status: 404,
          headers: { "Content-Type": "application/json" }
        })
      )
    );

    const request = apiGet("/api/customers/missing");

    await expect(request).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        message: "고객을 찾을 수 없습니다.",
        status: 404,
        body: { detail: "고객을 찾을 수 없습니다." }
      })
    );
    await expect(request).rejects.toBeInstanceOf(ApiError);
  });

  it("preserves AbortError so request lifecycles can suppress it", async () => {
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));

    await expect(apiGet("/api/customers")).rejects.toBe(abortError);
  });
});
