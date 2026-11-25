import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { daysBetween, money, niceCeil, num, pct, relativeTime, shortDate, signed } from "./format.ts";

describe("format", () => {
  it("formats money with sensible precision", () => {
    assert.equal(money(12.5), "$12.50");
    assert.equal(money(1234), "$1,234");
    assert.equal(money(2_500_000), "$2.5M");
    assert.equal(money(null), "–");
  });

  it("formats numbers and percentages", () => {
    assert.equal(num(1234.567, 1), "1,234.6");
    assert.equal(pct(0.1234), "12.3%");
    assert.equal(pct(0.05, 1, true), "+5.0%");
    assert.equal(pct(-0.05, 1, true), "−5.0%");
    assert.equal(signed(-12), "−12");
    assert.equal(signed(12), "+12");
    assert.equal(pct(Number.NaN), "–");
  });

  it("formats dates in UTC so server and client agree", () => {
    assert.equal(shortDate("2026-01-05"), "Jan 5");
    assert.equal(daysBetween("2026-01-01", "2026-01-08"), 7);
    assert.equal(shortDate(null), "–");
  });

  it("describes relative time", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    assert.equal(relativeTime("2026-01-01T11:59:30Z", now), "just now");
    assert.equal(relativeTime("2026-01-01T11:30:00Z", now), "30 min ago");
    assert.equal(relativeTime("2025-12-30T12:00:00Z", now), "2 d ago");
  });

  it("rounds axis maxima to nice numbers", () => {
    assert.equal(niceCeil(87), 100);
    assert.equal(niceCeil(230), 250);
    assert.equal(niceCeil(4100), 5000);
    assert.equal(niceCeil(0), 1);
  });
});
