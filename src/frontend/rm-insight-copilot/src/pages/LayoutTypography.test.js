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
