/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App, { DEMO_SESSION_KEY } from "./App.jsx";

vi.mock("./components/TopNav.jsx", () => ({
  default: () => <nav aria-label="서비스 내비게이션">RM navigation</nav>
}));
vi.mock("./pages/OverviewPage.jsx", () => ({
  default: () => <h1>Overview service</h1>
}));
vi.mock("./pages/DormancyRiskPage.jsx", () => ({
  default: () => <div>Risk service</div>
}));
vi.mock("./pages/PriorityPage.jsx", () => ({
  default: () => <div>Priority service</div>
}));
vi.mock("./pages/RecommendationsPage.jsx", () => ({
  default: () => <div>Recommendations service</div>
}));
vi.mock("./pages/AiReportPage.jsx", () => ({
  default: () => <div>Report service</div>
}));

function submitCredentials(username, password) {
  fireEvent.change(screen.getByLabelText("아이디"), {
    target: { value: username }
  });
  fireEvent.change(screen.getByLabelText("비밀번호"), {
    target: { value: password }
  });
  fireEvent.submit(screen.getByRole("form", { name: "RM Copilot 로그인" }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("App demo login flow", () => {
  it("starts on the login page when the tab has no authenticated session", () => {
    render(<App />);

    expect(
      screen.getByRole("form", { name: "RM Copilot 로그인" })
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("iM BANK intro animation")).not.toBeInTheDocument();
    expect(screen.queryByText("Overview service")).not.toBeInTheDocument();
  });

  it("keeps rejected credentials on the login page", () => {
    render(<App />);
    submitCredentials("wrong", "value");

    expect(screen.getByRole("alert")).toHaveTextContent(
      "아이디 또는 비밀번호가 일치하지 않습니다."
    );
    expect(window.sessionStorage).toHaveLength(0);
    expect(screen.queryByLabelText("iM BANK intro animation")).not.toBeInTheDocument();
  });

  it("plays the splash and then opens the service for test / 1234", () => {
    render(<App />);
    submitCredentials("test", "1234");

    expect(screen.getByLabelText("iM BANK intro animation")).toBeInTheDocument();
    expect(window.sessionStorage.getItem(DEMO_SESSION_KEY)).toBe("true");
    expect(window.sessionStorage).toHaveLength(1);

    act(() => vi.advanceTimersByTime(2700));

    expect(screen.getByText("Overview service")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "서비스 내비게이션" })).toBeInTheDocument();
  });

  it("restores an authenticated tab directly to the service", () => {
    window.sessionStorage.setItem(DEMO_SESSION_KEY, "true");

    render(<App />);

    expect(screen.getByText("Overview service")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "RM Copilot 로그인" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("iM BANK intro animation")).not.toBeInTheDocument();
  });
});
