/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import DormancyRiskPage from "./DormancyRiskPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

const options = {
  asOfMonth: "2025-06",
  segments: ["복합고관계", "수신중심"],
  riskBands: [
    { value: "G1_TOP_1", label: "상위 1%", order: 1 },
    { value: "G2_1_TO_3", label: "상위 1~3%", order: 2 }
  ],
  industries: [],
  regions: [],
  dedicatedOptions: [],
  weakeningTypes: []
};

const customer = {
  id: "CORP-REAL-02",
  name: "새봄유통",
  industry: "도소매",
  region: "부산",
  dedicated: "N",
  segment: "수신중심",
  riskBand: "G1_TOP_1",
  riskBandName: "상위 1%",
  riskBandOrder: 1,
  riskRank: 1,
  predictedPositive: true,
  threshold: 26.5,
  risk: 81.25,
  health: 18.75,
  clvRisk: 5.5,
  potentialLoss: 1.5,
  defenseRank: 2,
  weakeningType: "채널",
  signals: [{ label: "채널활동", change: -31.54, recent: 68, previous: 99 }]
};

function customerPage(items = [customer]) {
  return { items, page: 1, pageSize: 50, total: items.length };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DormancyRiskPage", () => {
  it("renders returned customers in the existing risk and signal components", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(path === "/api/filter-options" ? options : customerPage())
    );

    render(<DormancyRiskPage />);

    expect(await screen.findByText("새봄유통")).toBeInTheDocument();
    expect(screen.getByText("81.3%")).toBeInTheDocument();
    expect(screen.getByText("채널활동")).toBeInTheDocument();
    expect(screen.getByText("최근 68 / 이전 99")).toBeInTheDocument();
    expect(screen.getByText("단위: 백만원")).toHaveClass("amount-unit");
    expect(screen.getByText("-31.5%")).toBeInTheDocument();
    expect(screen.queryByText("-31.54%")).not.toBeInTheDocument();
    expect(
      screen.getAllByText("수신중심").find((element) => element.classList.contains("status-badge"))
    ).toHaveClass("status-badge", "blue");
    expect(screen.getByText("채널")).toHaveClass("status-badge", "blue");
    expect(
      screen.getAllByText("상위 1%").find((element) => element.classList.contains("status-badge"))
    ).toHaveClass("status-badge", "coral");
    expect(screen.getByRole("heading", { name: "지속거래약화 예측" })).toBeInTheDocument();
  });

  it("debounces search while applying segment and risk filters immediately", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(path === "/api/filter-options" ? options : customerPage())
    );
    render(<DormancyRiskPage />);
    await screen.findByText("새봄유통");

    fireEvent.change(screen.getByPlaceholderText("기업명 또는 법인ID 검색"), {
      target: { value: "새봄" }
    });

    expect(apiGet).not.toHaveBeenCalledWith(
      "/api/customers",
      expect.objectContaining({ search: "새봄" }),
      expect.anything()
    );
    await waitFor(
      () =>
        expect(apiGet).toHaveBeenCalledWith(
          "/api/customers",
          expect.objectContaining({ search: "새봄" }),
          expect.any(AbortSignal)
        ),
      { timeout: 700 }
    );

    fireEvent.change(screen.getByRole("combobox", { name: "세그먼트" }), {
      target: { value: "수신중심" }
    });
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(
        "/api/customers",
        expect.objectContaining({ search: "새봄", segment: "수신중심" }),
        expect.any(AbortSignal)
      )
    );

    fireEvent.change(screen.getByRole("combobox", { name: "위험도" }), {
      target: { value: "G1_TOP_1" }
    });
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(
        "/api/customers",
        expect.objectContaining({
          search: "새봄",
          segment: "수신중심",
          risk_band: "G1_TOP_1"
        }),
        expect.any(AbortSignal)
      )
    );
  });
});
