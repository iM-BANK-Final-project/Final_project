/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import RecommendationsPage from "./RecommendationsPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

const options = {
  asOfMonth: "2025-12",
  segments: ["복합고관계형"],
  riskLevels: ["HIGH", "MEDIUM", "WATCH"],
  industries: [],
  regions: [],
  dedicatedOptions: [],
  weakeningTypes: ["카드"]
};

const recommendationPage = {
  items: [
    {
      id: "CORP-A",
      name: "알파코",
      segment: "복합고관계형",
      priority: "HIGH",
      weakeningType: "카드",
      reason: "카드 거래 감소",
      contact: "이번 주 접촉",
      action: "결제 흐름 확인"
    }
  ],
  page: 1,
  pageSize: 50,
  total: 1
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RecommendationsPage", () => {
  it("filters recommendations by the selected risk level", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(path === "/api/filter-options" ? options : recommendationPage)
    );

    render(<RecommendationsPage />);

    await screen.findByText("알파코");
    fireEvent.change(screen.getByRole("combobox", { name: "위험도" }), {
      target: { value: "HIGH" }
    });

    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(
        "/api/recommendations",
        expect.objectContaining({ risk_level: "HIGH" }),
        expect.any(AbortSignal)
      )
    );
  });
});
