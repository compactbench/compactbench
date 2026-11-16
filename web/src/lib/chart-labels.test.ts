// node --test src/lib/*.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { frontier, hoverPlacement, labelWidth, placeLabels, type Bounds } from "./chart-labels.ts";

const bounds: Bounds = { left: 0, right: 640, top: 0, bottom: 300 };

test("a lone point is named to the right of its dot", () => {
  assert.deepEqual(placeLabels([{ x: 100, y: 100, text: "alpha", priority: 0 }], bounds), [
    { x: 109, y: 104, anchor: "start" },
  ]);
});

test("a name that would run off the right edge goes to the left", () => {
  const [spot] = placeLabels([{ x: 630, y: 100, text: "alpha", priority: 0 }], bounds);
  assert.equal(spot?.anchor, "end");
});

test("names never overlap: the later one moves, or waits for hover", () => {
  const points = [
    { x: 100, y: 100, text: "first-method", priority: 0 },
    { x: 100, y: 106, text: "second-method", priority: 1 },
  ];
  const [first, second] = placeLabels(points, bounds);
  assert.deepEqual(first, { x: 109, y: 104, anchor: "start" });
  assert.ok(second, "there is room on the left");
  assert.equal(second.anchor, "end");
});

test("priority decides who gets the name, not the order given", () => {
  const points = [
    { x: 100, y: 100, text: "low", priority: 5 },
    { x: 100, y: 100, text: "high", priority: 1 },
  ];
  const [low, high] = placeLabels(points, bounds, 1);
  assert.equal(low, null);
  assert.ok(high);
});

test("at most `limit` names are printed on a crowded chart", () => {
  const points = Array.from({ length: 40 }, (_, i) => ({
    x: 40 + (i % 8) * 75,
    y: 30 + Math.floor(i / 8) * 55,
    text: `m${i}`,
    priority: i,
  }));
  const placed = placeLabels(points, bounds, 10).filter(Boolean);
  assert.equal(placed.length, 10);
});

test("a name is not printed over another dot", () => {
  // Dots in a tight cross: every side of the middle one is covered.
  const points = [
    { x: 300, y: 150, text: "middle-one", priority: 9 },
    { x: 315, y: 150, text: "r", priority: 0 },
    { x: 285, y: 150, text: "l", priority: 0 },
    { x: 300, y: 138, text: "u", priority: 0 },
    { x: 300, y: 165, text: "d", priority: 0 },
  ];
  assert.equal(placeLabels(points, bounds)[0], null);
});

test("a hover name sits right of the dot, or left near the edge", () => {
  assert.equal(hoverPlacement({ x: 100, y: 50, text: "abc", priority: 0 }, bounds).anchor, "start");
  const near = 640 - labelWidth("abcdef");
  assert.equal(hoverPlacement({ x: near, y: 50, text: "abcdef", priority: 0 }, bounds).anchor, "end");
});

test("the frontier is the best score for the cost", () => {
  assert.deepEqual(
    frontier([
      { cost: 0, score: 0.1 }, // free and better than the other free one
      { cost: 0, score: 0.01 },
      { cost: 100, score: 0.6 },
      { cost: 110, score: 0.5 }, // costs more, scores less
      { cost: 300, score: 0.7 },
      { cost: 300, score: 0.7 }, // a tie stays on it
    ]),
    [true, false, true, false, true, true],
  );
});
