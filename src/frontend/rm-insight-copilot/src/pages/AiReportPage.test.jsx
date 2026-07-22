/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost, apiPostBlob } from "../api/client.js";
import AiReportPage from "./AiReportPage.jsx";

vi.mock("../api/client.js", () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPostBlob: vi.fn()
}));

const options = {
  asOfMonth: "2025-06",
  segments: [],
  riskLevels: [],
  industries: [],
  regions: [],
  dedicatedOptions: [],
  weakeningTypes: []
};

const listedCustomer = {
  id: "CORP-A",
  name: "알파코",
  risk: 72.5
};

const generatedReport = {
  corporateId: "CORP-A",
  customerName: "알파코",
  asOfMonth: "2025-06",
  generatedAt: "2026-07-21T15:00:00+09:00",
  metrics: { risk: 72.55, clvRisk: 100, potentialLoss: 30 },
  shapFactors: Array.from({ length: 10 }, (_, index) => ({
    feature: `feature_${index + 1}`,
    featureValue: null,
    impact: (10 - index) / 100,
    rank: index + 1
  })),
  riskSummary: "조기 관리가 필요합니다.",
  valueAssessment: "확정 손실이 아닌 시나리오입니다.",
  weakeningDrivers: "입출금과 채널 예측 기여도를 확인합니다.",
  contactStrategy: "RM이 거래 변화 배경을 확인합니다.",
  recommendedActions: ["접촉 일정 수립", "변화 사유 확인"],
  caveats: ["SHAP은 인과관계가 아닙니다."]
};

function mockStoredReport(customers = [listedCustomer], signals = []) {
  apiGet.mockImplementation((path) => {
    if (path === "/api/filter-options") return Promise.resolve(options);
    if (path === "/api/customers") {
      return Promise.resolve({ items: customers, page: 1, pageSize: 200, total: customers.length });
    }
    if (path.startsWith("/api/reports/")) {
      const id = decodeURIComponent(path.split("/").at(-1));
      const customer = customers.find((item) => item.id === id) ?? listedCustomer;
      return Promise.resolve({
        customer: { ...customer, signals },
        recommendation: null,
        strategySummary: "저장된 요약 문장입니다.",
        shapAvailable: true,
        shapFactors: generatedReport.shapFactors
      });
    }
    return Promise.reject(new Error(`Unexpected path ${path}`));
  });
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("AiReportPage", () => {
  it("renders a partial stored report without breaking the page", async () => {
    apiGet.mockImplementation((path) => {
      if (path === "/api/filter-options") return Promise.resolve(options);
      if (path === "/api/customers") {
        return Promise.resolve({ items: [listedCustomer], page: 1, pageSize: 200, total: 1 });
      }
      if (path === "/api/reports/CORP-A") {
        return Promise.resolve({
          customer: {
            ...listedCustomer,
            signals: []
          },
          recommendation: null,
          strategySummary: "저장된 요약 문장입니다.",
          shapAvailable: false,
          shapFactors: []
        });
      }

      return Promise.reject(new Error(`Unexpected path ${path}`));
    });

    render(<AiReportPage />);

    expect(
      screen.getByRole("heading", { name: "지속거래약화 전략 보고서" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "저장된 지속거래약화 전략 보고서" })
    ).not.toBeInTheDocument();
    expect(await screen.findByText("알파코")).toBeInTheDocument();
    expect(screen.getByText("저장된 요약 문장입니다.")).toBeInTheDocument();
    expect(screen.getByText("저장된 약화 신호가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("저장된 추천 접촉 전략이 없습니다.")).toBeInTheDocument();
  });

  it("shows the SHAP title and all ten factors without collapsing", async () => {
    const shapFactors = Array.from({ length: 10 }, (_, index) => ({
      feature: `feature_${index + 1}`,
      featureValue: null,
      impact: (10 - index) / 100,
      rank: index + 1
    }));
    apiGet.mockImplementation((path) => {
      if (path === "/api/filter-options") return Promise.resolve(options);
      if (path === "/api/customers") {
        return Promise.resolve({ items: [listedCustomer], page: 1, pageSize: 200, total: 1 });
      }
      if (path === "/api/reports/CORP-A") {
        return Promise.resolve({
          customer: { ...listedCustomer, signals: [] },
          recommendation: null,
          strategySummary: "저장된 요약 문장입니다.",
          shapAvailable: true,
          shapFactors
        });
      }
      return Promise.reject(new Error(`Unexpected path ${path}`));
    });

    render(<AiReportPage />);

    expect(
      await screen.findByText("주요 SHAP Value (상위 10개)")
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("shap-factor")).toHaveLength(10);
    expect(screen.queryByRole("button", { name: /더 보기/ })).not.toBeInTheDocument();
  });

  it("generates and renders all six fixed AI report sections", async () => {
    mockStoredReport();
    let resolveGeneration;
    apiPost.mockReturnValue(new Promise((resolve) => {
      resolveGeneration = resolve;
    }));
    render(<AiReportPage />);
    await screen.findByText("저장된 요약 문장입니다.");
    const button = await screen.findByRole("button", { name: "전략 보고서 생성" });

    fireEvent.click(button);

    expect(screen.getByRole("button", { name: "보고서 생성 중..." })).toBeDisabled();
    expect(apiPost).toHaveBeenCalledWith(
      "/api/reports/CORP-A/generate",
      {},
      { as_of_month: "2025-06" }
    );
    resolveGeneration(generatedReport);

    expect(await screen.findByText("AI 종합 위험 요약")).toBeInTheDocument();
    expect(screen.getByText("고객가치 및 잠재손실 해석")).toBeInTheDocument();
    expect(screen.getByText("주요 약화 원인")).toBeInTheDocument();
    expect(screen.getByText("RM 접촉 전략")).toBeInTheDocument();
    expect(screen.getByText("실행 권고사항")).toBeInTheDocument();
    expect(screen.getByText("분석 유의사항")).toBeInTheDocument();
    expect(screen.getByText("72.6%")).toBeInTheDocument();
    expect(screen.getByText("100 백만원")).toBeInTheDocument();
    expect(screen.getByText("30 백만원")).toBeInTheDocument();
    expect(screen.getByText("선택 고객 저장 리포트")).toHaveClass("blue");
    const aiReportBadge = screen.getByText("AI Report");
    const generatedCard = aiReportBadge.closest("section");
    const reportLayout = generatedCard?.parentElement;

    expect(aiReportBadge).toHaveClass("violet");
    expect(screen.queryByText("Gemini AI Report")).not.toBeInTheDocument();
    expect(generatedCard).toHaveClass("panel", "report-card", "generated-ai-report");
    expect(reportLayout).toHaveClass("report-layout");
    expect(reportLayout?.children).toHaveLength(3);
    expect(reportLayout?.lastElementChild).toBe(generatedCard);
    expect(screen.getByText("선택 고객 저장 리포트").closest(".report-card"))
      .toHaveTextContent("단위: 백만원");
    expect(generatedCard).toHaveTextContent("단위: 백만원");
    expect(screen.getByRole("button", { name: "PDF 다운로드" })).toBeInTheDocument();
  });

  it("shows stored signal percentages with at most one decimal place", async () => {
    mockStoredReport([listedCustomer], [
      { label: "채널", change: -31.54, recent: 68, previous: 99 }
    ]);

    render(<AiReportPage />);

    expect(await screen.findByText("-31.5%")).toBeInTheDocument();
    expect(screen.queryByText("-31.54%")).not.toBeInTheDocument();
  });

  it("keeps the stored report and allows retry after generation failure", async () => {
    mockStoredReport();
    apiPost
      .mockRejectedValueOnce(new Error("AI 보고서 생성에 실패했습니다."))
      .mockResolvedValueOnce(generatedReport);
    render(<AiReportPage />);

    fireEvent.click(await screen.findByRole("button", { name: "전략 보고서 생성" }));

    expect(await screen.findByText("AI 보고서 생성에 실패했습니다.")).toBeInTheDocument();
    expect(screen.getByText("저장된 요약 문장입니다.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "보고서 생성 재시도" }));

    expect(await screen.findByText("AI 종합 위험 요약")).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledTimes(2);
  });

  it("downloads the displayed report and revokes the object URL", async () => {
    mockStoredReport();
    apiPost.mockResolvedValue(generatedReport);
    apiPostBlob.mockResolvedValue({
      blob: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
      filename: "알파코_AI_전략_보고서.pdf"
    });
    const createObjectURL = vi.fn().mockReturnValue("blob:report");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<AiReportPage />);
    fireEvent.click(await screen.findByRole("button", { name: "전략 보고서 생성" }));
    fireEvent.click(await screen.findByRole("button", { name: "PDF 다운로드" }));

    await waitFor(() => expect(apiPostBlob).toHaveBeenCalledWith(
      "/api/reports/CORP-A/pdf",
      generatedReport
    ));
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
    click.mockRestore();
  });

  it("clears a generated report when the selected customer changes", async () => {
    const second = { ...listedCustomer, id: "CORP-B", name: "베타코" };
    mockStoredReport([listedCustomer, second]);
    apiPost.mockResolvedValue(generatedReport);
    render(<AiReportPage />);
    fireEvent.click(await screen.findByRole("button", { name: "전략 보고서 생성" }));
    expect(await screen.findByText("AI 종합 위험 요약")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("보고서 고객"), { target: { value: "CORP-B" } });

    await waitFor(() => expect(screen.queryByText("AI 종합 위험 요약")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "PDF 다운로드" })).not.toBeInTheDocument();
  });
});
