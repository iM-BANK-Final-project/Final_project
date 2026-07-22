import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("keeps the amount unit pill at its content width inside a grid", () => {
  const stylesheet = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  const amountUnitRule = stylesheet.match(/\.amount-unit\s*\{([\s\S]*?)\}/)?.[1] ?? "";

  expect(amountUnitRule).toMatch(/width:\s*fit-content/);
  expect(amountUnitRule).toMatch(/justify-self:\s*start/);
});
