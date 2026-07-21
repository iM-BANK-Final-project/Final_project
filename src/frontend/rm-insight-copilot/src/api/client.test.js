import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet, apiPost, apiPostBlob } from "./client.js";

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

describe("API POST helpers", () => {
  it("posts JSON with query parameters and returns JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ riskSummary: "요약" }), {
        status: 200,
        headers: { "content-type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiPost(
      "/api/reports/A/generate",
      { requested: true },
      { as_of_month: "2025-12" }
    );

    expect(result).toEqual({ riskSummary: "요약" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/A/generate?as_of_month=2025-12",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requested: true })
      })
    );
  });

  it("raises a safe ApiError from a failed JSON response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "AI 보고서 생성에 실패했습니다." }), {
          status: 502,
          headers: { "content-type": "application/json" }
        })
      )
    );

    await expect(apiPost("/api/reports/A/generate", null)).rejects.toEqual(
      expect.objectContaining({
        name: "ApiError",
        status: 502,
        message: "AI 보고서 생성에 실패했습니다."
      })
    );
  });

  it("returns a PDF blob and decodes an RFC 5987 filename", async () => {
    const filename = "에이기업_AI_전략_보고서_2025-12.pdf";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new Blob(["%PDF-1.4"], { type: "application/pdf" }), {
          status: 200,
          headers: {
            "content-type": "application/pdf",
            "content-disposition": `attachment; filename="fallback.pdf"; filename*=UTF-8''${encodeURIComponent(filename)}`
          }
        })
      )
    );

    const result = await apiPostBlob("/api/reports/A/pdf", { corporateId: "A" });

    expect(result.filename).toBe(filename);
    expect(result.blob.type).toBe("application/pdf");
  });

  it("uses a plain safe filename and falls back when none is supplied", async () => {
    const responses = [
      new Response(new Blob(["pdf"]), {
        headers: { "content-disposition": "attachment; filename=report_A.pdf" }
      }),
      new Response(new Blob(["pdf"]))
    ];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(responses.shift())));

    expect((await apiPostBlob("/first", {})).filename).toBe("report_A.pdf");
    expect((await apiPostBlob("/second", {})).filename).toBe("ai_strategy_report.pdf");
  });

  it("parses JSON errors instead of returning an error blob", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "PDF 보고서 생성에 실패했습니다." }), {
          status: 500,
          headers: { "content-type": "application/json" }
        })
      )
    );

    await expect(apiPostBlob("/api/reports/A/pdf", {})).rejects.toBeInstanceOf(ApiError);
  });
});
