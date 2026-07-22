/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import StatusBadge from "./StatusBadge.jsx";

afterEach(cleanup);

describe("StatusBadge", () => {
  it.each([
    ["복합고관계형", "mint"],
    ["거래·수신중심형", "blue"],
    ["저거래·저수신형", "gray"]
  ])("uses a stable segment tone for %s", (value, tone) => {
    render(<StatusBadge kind="segment" value={value}>{value}</StatusBadge>);

    expect(screen.getByText(value)).toHaveClass(tone);
  });

  it.each([
    ["입출금", "coral"],
    ["자동이체", "amber"],
    ["채널", "blue"],
    ["카드", "violet"],
    ["복합 거래활동", "mint"]
  ])("uses a stable weakening tone for %s", (value, tone) => {
    render(<StatusBadge kind="weakening" value={value}>{value}</StatusBadge>);

    expect(screen.getByText(value)).toHaveClass(tone);
  });

  it("distinguishes stored and generated report stages", () => {
    render(
      <>
        <StatusBadge kind="stage" value="stored">선택 고객 저장 리포트</StatusBadge>
        <StatusBadge kind="stage" value="generated">Gemini AI Report</StatusBadge>
      </>
    );

    expect(screen.getByText("선택 고객 저장 리포트")).toHaveClass("blue");
    expect(screen.getByText("Gemini AI Report")).toHaveClass("violet");
  });
});
