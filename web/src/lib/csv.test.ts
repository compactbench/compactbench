// node --test src/lib/*.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { cell, toCsv } from "./csv.ts";

test("cells are quoted and guarded against formulas", () => {
  assert.equal(cell("plain"), "plain");
  assert.equal(cell('a "b", c'), '"a ""b"", c"');
  assert.equal(cell("=HYPERLINK(1)"), "'=HYPERLINK(1)");
  assert.equal(cell("@SUM(A1)"), "'@SUM(A1)");
  assert.equal(cell("-1+2"), "'-1+2");
  assert.equal(cell(-0.5), "-0.5", "numbers are not text");
  assert.equal(cell(null), "");
  assert.equal(cell(Number.NaN), "");
  assert.equal(toCsv(["a", "b"], [[1, "x\ny"]]), 'a,b\r\n1,"x\ny"\r\n');
});
