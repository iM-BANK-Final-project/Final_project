/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet } from "../api/client.js";
import PriorityPage from "./PriorityPage.jsx";

vi.mock("../api/client.js", () => ({ apiGet: vi.fn() }));

const options = {
  industries: ["제조업"],
  regions: ["대구"],
  dedicatedOptions: ["Y", "N"],
  weakeningTypes: ["복합 거래활동"],
  segments: ["저거래·저수신형"]
};

const customers = [
  {
    id: "CORP-A",
    name: "에이기업",
    industry: "제조업",
    region: "대구",
    dedicated: "Y",
    segment: "저거래·저수신형",
    riskBand: "G1_TOP_1",
    riskBandName: "상위 1%",
    risk: 80,
    health: 20,
    clvRisk: 70.25,
    potentialLoss: 30.5,
    defenseRank: 1,
    weakeningType: "복합 거래활동",
    signals: []
  },
  {
    id: "CORP-B",
    name: "비기업",
    industry: "제조업",
    region: "대구",
    dedicated: "N",
    segment: "저거래·저수신형",
    riskBand: "G5_REST",
    riskBandName: "나머지 90%",
    risk: 10,
    health: 90,
    clvRisk: -8,
    potentialLoss: -2,
    defenseRank: null,
    weakeningType: "카드",
    signals: []
  }
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PriorityPage", () => {
  it("renders CLV risk, potential loss, and nullable defense ranks", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(
        path === "/api/filter-options"
          ? options
          : { items: customers, page: 1, pageSize: 50, total: 2 }
      )
    );

    render(<PriorityPage onRecommendationOpen={vi.fn()} />);

    expect(await screen.findByText("CLV_Risk")).toBeInTheDocument();
    expect(screen.getByText("PotentialLoss")).toBeInTheDocument();
    expect(screen.getByText("방어순위")).toBeInTheDocument();
    expect(screen.getByText("70.25")).toBeInTheDocument();
    expect(screen.getByText("30.5")).toBeInTheDocument();
    expect(
      screen.getByText(
        "최근 6개월 실제 FISIM을 위험확률로 조정한 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText("고객가치 대리지표")).not.toBeInTheDocument();
    expect(screen.queryByText("CRM 우선순위 점수")).not.toBeInTheDocument();
    expect(screen.queryByText("수익성")).not.toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(table).toHaveClass("priority-table");
    expect(table.parentElement).toHaveClass("priority-table-panel");
    expect(table.parentElement).toHaveTextContent("단위: 백만원");
    expect(table.querySelectorAll("col")).toHaveLength(11);
  });

  it("keeps filters and recommendation navigation", async () => {
    apiGet.mockImplementation((path) =>
      Promise.resolve(
        path === "/api/filter-options"
          ? options
          : { items: customers, page: 1, pageSize: 50, total: 2 }
      )
    );
    const onRecommendationOpen = vi.fn();
    render(<PriorityPage onRecommendationOpen={onRecommendationOpen} />);

    await screen.findByText("CLV_Risk");
    fireEvent.change(screen.getByRole("combobox", { name: "업종" }), {
      target: { value: "제조업" }
    });
    fireEvent.click(screen.getAllByRole("button", { name: "추천 보기" })[0]);

    expect(onRecommendationOpen).toHaveBeenCalledWith("CORP-A");
    expect(apiGet).toHaveBeenCalledWith(
      "/api/priorities",
      expect.objectContaining({ industry: "제조업" }),
      expect.any(AbortSignal)
    );
  });
});
