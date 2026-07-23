/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import OverviewPage from "./OverviewPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

const overview = {
  asOfMonth: "2025-12",
  managedCustomerCount: 27,
  averageRisk: 63.25,
  thresholdShare: 18.4,
  potentialLossTotal: 12.345,
  monthlyTrend: [
    { month: "2025-07", risk: 3.7, thresholdShare: 0.2, thresholdCount: 7, eligibleCount: 3347, isCurrent: false },
    { month: "2025-08", risk: 4.3, thresholdShare: 0.2, thresholdCount: 6, eligibleCount: 3348, isCurrent: false },
    { month: "2025-09", risk: 3.9, thresholdShare: 0.4, thresholdCount: 12, eligibleCount: 3348, isCurrent: false },
    { month: "2025-10", risk: 4.1, thresholdShare: 0.3, thresholdCount: 10, eligibleCount: 3345, isCurrent: false },
    { month: "2025-11", risk: 4.6, thresholdShare: 0.3, thresholdCount: 11, eligibleCount: 3344, isCurrent: false },
    { month: "2025-12", risk: 3.5, thresholdShare: 0.4, thresholdCount: 15, eligibleCount: 3341, isCurrent: true }
  ],
  signalSummary: [
    { label: "입출금", value: 12 },
    { label: "채널", value: 9 }
  ]
};

const topCustomer = {
  id: "000fd5948a0ec34ce399733e5f9ce20477d0037286c99f4e",
  name: "한빛산업주식회사대구본점",
  industry: "제조업",
  region: "서울",
  dedicated: "Y",
  segment: "복합고관계",
  riskBand: "G1_TOP_1",
  riskBandName: "상위 1%",
  risk: 81.25,
  health: 18.75,
  clvRisk: 7.5,
  potentialLoss: 2.5,
  defenseRank: 1,
  weakeningType: "입출금",
  signals: []
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OverviewPage", () => {
  it("renders API KPI values and the top priority customer", async () => {
    apiGet.mockImplementation((path) => {
      if (path === "/api/overview") return Promise.resolve(overview);
      if (path === "/api/customers") {
        return Promise.resolve({ items: [topCustomer], page: 1, pageSize: 1, total: 1 });
      }
      throw new Error(`Unexpected path: ${path}`);
    });

    render(<OverviewPage onPageChange={vi.fn()} />);

    const customerName = await screen.findByRole("button", { name: /기업명 전체 보기/ });
    expect(customerName).toHaveTextContent(/^한빛산업주식회사$/);
    fireEvent.click(customerName);
    expect(customerName).toHaveTextContent(topCustomer.name);
    const customerId = screen.getByRole("button", { name: /법인ID 전체 보기/ });
    expect(customerId).toHaveTextContent(/^000fd594$/);
    fireEvent.click(customerId);
    expect(customerId).toHaveTextContent(topCustomer.id);
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.getByText("63.3%")).toBeInTheDocument();
    expect(screen.getByText("18.4%")).toBeInTheDocument();
    expect(screen.getByText("12.35")).toBeInTheDocument();
    expect(screen.getByText("잠재손실 방어대상 합계")).toBeInTheDocument();
    const potentialLossCard = screen.getByText("잠재손실 방어대상 합계").closest(".kpi-card");
    expect(potentialLossCard).toHaveClass("blue");
    expect(potentialLossCard?.parentElement).toHaveClass("overview-kpi-grid");
    expect(potentialLossCard).toHaveTextContent("단위: 백만원");
    const potentialLossValue = potentialLossCard?.querySelector(".kpi-value");
    const amountUnit = potentialLossCard?.querySelector(".amount-unit");
    expect(potentialLossValue?.nextElementSibling).toBe(amountUnit);
    expect(screen.getByText("FISIM 기반 추정치")).toBeInTheDocument();
    expect(screen.queryByText(/확정 회계손실이 아닙니다/)).not.toBeInTheDocument();
    const signalPanel = screen.getByRole("heading", { name: "주요 약화 신호" }).closest(".panel");
    const depositSignal = within(signalPanel).getByText("입출금").closest(".rank-item");
    expect(depositSignal).toHaveClass("signal-rank-item");
    expect(depositSignal?.querySelector(".signal-dot")).toHaveClass("coral");
    expect(depositSignal?.querySelector(".signal-count")).toHaveTextContent("12건");
    expect(depositSignal?.querySelector(".status-badge")).not.toBeInTheDocument();
    expect(screen.queryByText("알파코")).not.toBeInTheDocument();
    const trendChart = screen.getByRole("group", { name: "월별 지속거래약화 위험 추세" });
    expect(within(trendChart).getByText("평균 위험")).toBeInTheDocument();
    expect(within(trendChart).getByText("모델 임계값 이상 비중")).toBeInTheDocument();
    expect(within(trendChart).getByText("현재 기준")).toBeInTheDocument();
    expect(within(trendChart).getByText("3.5%")).toBeInTheDocument();
    expect(trendChart.querySelector(".risk-trend-label.is-current")).toHaveTextContent("15명");
  });

  it("keeps both overview navigation actions", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(
        path === "/api/overview"
          ? overview
          : { items: [topCustomer], page: 1, pageSize: 1, total: 1 }
      )
    );
    const onPageChange = vi.fn();

    render(<OverviewPage onPageChange={onPageChange} />);
    await screen.findByRole("button", { name: /기업명 전체 보기/ });
    fireEvent.click(screen.getByRole("button", { name: "관리 우선순위" }));
    fireEvent.click(screen.getByRole("button", { name: "약화 신호 보기" }));

    expect(onPageChange).toHaveBeenNthCalledWith(1, "priority");
    expect(onPageChange).toHaveBeenNthCalledWith(2, "risk");
  });

  it("shows loading and error states without mock customer content", async () => {
    const pending = new Promise(() => {});
    apiGet.mockReturnValue(pending);
    const { unmount } = render(<OverviewPage onPageChange={vi.fn()} />);

    expect(screen.getByRole("status")).toHaveTextContent("데이터를 불러오는 중입니다.");
    expect(screen.queryByText("알파코")).not.toBeInTheDocument();
    unmount();

    apiGet.mockRejectedValue(new Error("요약 조회 실패"));
    render(<OverviewPage onPageChange={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("요약 조회 실패");
    expect(screen.queryByText("알파코")).not.toBeInTheDocument();
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
  });
});
