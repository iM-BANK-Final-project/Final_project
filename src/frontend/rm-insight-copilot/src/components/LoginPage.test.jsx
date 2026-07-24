/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./LoginPage.jsx";

afterEach(cleanup);

describe("LoginPage", () => {
  it("exposes the brand and form panels for the responsive login layout", () => {
    const { container } = render(<LoginPage onLogin={vi.fn()} />);

    expect(screen.getByTestId("login-page")).toHaveClass("login-page");
    expect(container.querySelector(".login-brand-panel")).toBeInTheDocument();
    expect(container.querySelector(".login-form-panel")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "iM Bank RM Copilot" })
    ).toBeInTheDocument();
  });

  it("does not show the local demo note", () => {
    render(<LoginPage onLogin={vi.fn()} />);

    expect(screen.queryByText("로컬 시연용 데모 로그인")).not.toBeInTheDocument();
  });

  it("shows an inline error when the submitted demo credentials are rejected", () => {
    const onLogin = vi.fn(() => false);

    render(<LoginPage onLogin={onLogin} />);
    fireEvent.change(screen.getByLabelText("아이디"), {
      target: { value: "wrong" }
    });
    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: "value" }
    });
    fireEvent.submit(screen.getByRole("form", { name: "RM Copilot 로그인" }));

    expect(onLogin).toHaveBeenCalledWith("wrong", "value");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "아이디 또는 비밀번호가 일치하지 않습니다."
    );
  });

  it("does not show an error when the submitted demo credentials are accepted", () => {
    const onLogin = vi.fn(() => true);

    render(<LoginPage onLogin={onLogin} />);
    fireEvent.change(screen.getByLabelText("아이디"), {
      target: { value: "test" }
    });
    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: "1234" }
    });
    fireEvent.submit(screen.getByRole("form", { name: "RM Copilot 로그인" }));

    expect(onLogin).toHaveBeenCalledWith("test", "1234");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("toggles password visibility", () => {
    render(<LoginPage onLogin={vi.fn()} />);
    const password = screen.getByLabelText("비밀번호");

    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 표시" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "비밀번호 숨기기" })).toBeInTheDocument();
  });
});
