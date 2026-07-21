/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import OverviewPage from "./OverviewPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

const overview = {
  asOfMonth: "2025-06",
  managedCustomerCount: 27,
  averageRisk: 63.25,
  highRiskShare: 18.4,
  potentialLossTotal: 12.345,
  monthlyTrend: [
    { month: "2025-05", risk: 0, managed: 20 },
    { month: "2025-06", risk: 63.25, managed: 27 }
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
  riskLevel: "고위험",
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
    expect(screen.getByText(/확정 회계손실이 아닙니다/)).toBeInTheDocument();
    expect(screen.queryByText("알파코")).not.toBeInTheDocument();
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
