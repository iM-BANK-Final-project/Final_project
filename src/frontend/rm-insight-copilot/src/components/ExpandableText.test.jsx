/* @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ExpandableText from "./ExpandableText.jsx";

afterEach(cleanup);

describe("ExpandableText", () => {
  it("shows only the first 8 characters while collapsed and the full text when expanded", () => {
    render(
      <ExpandableText
        text="000fd5948a0ec34ce399733e5f9ce20477d0037286c99f4e"
        label="법인ID"
      />
    );

    const text = screen.getByRole("button", { name: /법인ID 전체 보기/ });

    expect(text).toHaveTextContent(/^000fd594$/);

    fireEvent.click(text);

    expect(text).toHaveTextContent("000fd5948a0ec34ce399733e5f9ce20477d0037286c99f4e");
  });

  it("toggles from collapsed to expanded when the text area is clicked", () => {
    render(
      <ExpandableText
        text="000fd5948a0ec34ce399733e5f9ce20477d0037286c99f4e"
        label="법인ID"
      />
    );

    const text = screen.getByRole("button", { name: /법인ID 전체 보기/ });

    expect(text).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(text);

    expect(text).toHaveAttribute("aria-expanded", "true");
    expect(text).toHaveClass("is-expanded");
  });
});
