/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import AiReportPage from "./AiReportPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
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
});
