// Which dots on a scatter chart get a printed name, and where it goes. Names are tried in
// priority order beside their dot (right, left, above, below); a name that would overlap one
// already placed, another dot or the plot edge is left unprinted (the chart shows it on
// hover), and at most `limit` names are printed so a crowded board stays readable.

export interface LabelPoint {
  x: number;
  y: number;
  text: string;
  /** Lower goes first. */
  priority: number;
}

export interface Placement {
  x: number;
  y: number;
  anchor: "start" | "end" | "middle";
}

export interface Bounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

interface Box {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** Average width of one character of an 11px label, in chart units. */
const CHAR = 6.2;
/** Half the space a dot takes, with its outline. */
const DOT = 7;
const GAP = 2;

export const labelWidth = (text: string): number => text.length * CHAR;

function candidates(p: LabelPoint): [Placement, Box][] {
  const w = labelWidth(p.text);
  // Boxes run from 9 units above the text baseline to 3 below it.
  const box = (x0: number, baseline: number): Box => ({ x0, x1: x0 + w, y0: baseline - 9, y1: baseline + 3 });
  return [
    [{ x: p.x + 9, y: p.y + 4, anchor: "start" }, box(p.x + 9, p.y + 4)],
    [{ x: p.x - 9, y: p.y + 4, anchor: "end" }, box(p.x - 9 - w, p.y + 4)],
    [{ x: p.x, y: p.y - 11, anchor: "middle" }, box(p.x - w / 2, p.y - 11)],
    [{ x: p.x, y: p.y + 20, anchor: "middle" }, box(p.x - w / 2, p.y + 20)],
  ];
}

const overlaps = (a: Box, b: Box): boolean =>
  a.x0 < b.x1 + GAP && b.x0 < a.x1 + GAP && a.y0 < b.y1 + GAP && b.y0 < a.y1 + GAP;

const inside = (a: Box, b: Bounds): boolean =>
  a.x0 >= b.left && a.x1 <= b.right && a.y0 >= b.top && a.y1 <= b.bottom;

/** A placement per point (same order as `points`), or null where the name isn't printed. */
export function placeLabels(points: LabelPoint[], bounds: Bounds, limit = 10): (Placement | null)[] {
  const dots: Box[] = points.map((p) => ({ x0: p.x - DOT, x1: p.x + DOT, y0: p.y - DOT, y1: p.y + DOT }));
  const placed: Box[] = [];
  const result: (Placement | null)[] = points.map(() => null);
  const order = points.map((_, i) => i).sort((a, b) => points[a].priority - points[b].priority);
  for (const i of order) {
    if (placed.length >= limit) break;
    for (const [placement, box] of candidates(points[i])) {
      const clear =
        inside(box, bounds) &&
        !placed.some((other) => overlaps(box, other)) &&
        !dots.some((dot, j) => j !== i && overlaps(box, dot));
      if (clear) {
        result[i] = placement;
        placed.push(box);
        break;
      }
    }
  }
  return result;
}

/** Where a name goes when it is only shown on hover: right of the dot, or left near the edge. */
export function hoverPlacement(p: LabelPoint, bounds: Bounds): Placement {
  return p.x + 9 + labelWidth(p.text) <= bounds.right
    ? { x: p.x + 9, y: p.y + 4, anchor: "start" }
    : { x: p.x - 9, y: p.y + 4, anchor: "end" };
}

/**
 * The best-value points: no other point scores at least as high for no more cost (with one
 * of the two strictly better). These are the ones worth naming on a score-vs-cost chart.
 */
export function frontier(points: { cost: number; score: number }[]): boolean[] {
  return points.map((p) =>
    !points.some((q) => q.cost <= p.cost && q.score >= p.score && (q.cost < p.cost || q.score > p.score)),
  );
}
