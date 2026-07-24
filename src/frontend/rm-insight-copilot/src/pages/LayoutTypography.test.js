import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

const stylesheet = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

it("uses regular weight for both overview content headings", () => {
  const rule = stylesheet.match(
    /\.overview-content \.section-header h2\s*\{([\s\S]*?)\}/
  )?.[1] ?? "";

  expect(rule).toMatch(/font-weight:\s*var\(--weight-regular\)/);
});

it("uses regular weight throughout the CRM priority table", () => {
  const rule = stylesheet.match(
    /\.priority-table th,\s*\.priority-table td,([\s\S]*?)\{([\s\S]*?)\}/
  )?.[2] ?? "";

  expect(rule).toMatch(/font-weight:\s*var\(--weight-regular\)/);
  expect(stylesheet).toMatch(
    /\.priority-table \.expandable-text\.is-expanded\s*\{[\s\S]*?font-weight:\s*var\(--weight-regular\)/
  );
});

it("centers the CRM defense rank column", () => {
  const rule = stylesheet.match(
    /\.priority-table th:first-child,\s*\.priority-table td:first-child\s*\{([\s\S]*?)\}/
  )?.[1] ?? "";

  expect(rule).toMatch(/text-align:\s*center/);
});

it("uses a fixed iM Bank background across the five service pages", () => {
  const rootRule = stylesheet.match(/:root\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  const appShellRule = stylesheet.match(/\.app-shell\s*\{([\s\S]*?)\}/)?.[1] ?? "";

  expect(rootRule).toMatch(/--app-bg-base:\s*#f5fbf9/);
  expect(rootRule).toMatch(/--app-bg-mint:\s*rgba\(0,\s*199,\s*169,\s*0\.13\)/);
  expect(rootRule).toMatch(/--app-bg-lime:\s*rgba\(166,\s*222,\s*94,\s*0\.1\)/);
  expect(appShellRule).toMatch(/var\(--app-bg-mint\)/);
  expect(appShellRule).toMatch(/var\(--app-bg-lime\)/);
  expect(appShellRule).toMatch(/var\(--app-bg-base\)/);
  expect(appShellRule).toMatch(/background-attachment:\s*fixed/);
});

it("keeps the login page background independent", () => {
  const loginRule = stylesheet.match(/\.login-page\s*\{([\s\S]*?)\}/)?.[1] ?? "";

  expect(loginRule).toMatch(/background:\s*#fff/);
});

it("uses the high-contrast iM Bank mint and lime palette in the overview trend", () => {
  const rootRule = stylesheet.match(/:root\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  const lineRule = stylesheet.match(/\.risk-trend-line\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  const barRule = stylesheet.match(/\.risk-trend-bar\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  const currentBarRule = stylesheet.match(
    /\.risk-trend-bar\.is-current\s*\{([\s\S]*?)\}/
  )?.[1] ?? "";

  expect(rootRule).toMatch(/--mint-deep:\s*#007f6d/);
  expect(lineRule).toMatch(/stroke:\s*var\(--mint-deep\)/);
  expect(lineRule).toMatch(/stroke-width:\s*5/);
  expect(barRule).toMatch(/var\(--lime\)/);
  expect(barRule).toMatch(/var\(--mint\)/);
  expect(barRule).not.toMatch(/stroke:/);
  expect(currentBarRule).toMatch(/fill:\s*var\(--mint\)/);
  expect(currentBarRule).not.toMatch(/stroke:/);
});
