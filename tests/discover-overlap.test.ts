// Gate for tesser-discover/scripts/overlap.py — the deterministic core of the
// discovery skill. overlap.py is stdlib-only python3 (no venv), so we spawn it
// via `python3` directly, the same way SKILL.md invokes it.
//
// Two things are pinned here:
//   1. The skill's own Python unit tests (test_overlap.py) pass — run inside the
//      vitest suite so `npm run test` actually exercises them (they are Python,
//      so vitest would otherwise never see them). Mirrors check-review.test.ts.
//   2. The bare `python3 scripts/overlap.py <ledger>` contract resolves from the
//      SKILL's own directory (cwd = tesser-discover/), and returns the right exit
//      code on a healthy ledger (0) and a collapsed/baseline-reproducing one (1).

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const skillDir = path.join(repoRoot, "tesser-discover");
const overlapPy = path.join(skillDir, "scripts", "overlap.py");
const testOverlapPy = path.join(skillDir, "scripts", "test_overlap.py");

let tmp: string;
let n = 0;

beforeAll(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), "td-overlap-"));
});
afterAll(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

function writeLedger(led: unknown): string {
  const p = path.join(tmp, `ledger-${n++}.json`);
  fs.writeFileSync(p, JSON.stringify(led));
  return p;
}

// Invoke exactly as the agent does: `cd tesser-discover && python3 scripts/overlap.py <ledger>`.
// cwd = the skill dir proves the bare `scripts/overlap.py` reference resolves locally.
function runGate(ledgerPath: string) {
  return spawnSync("python3", ["scripts/overlap.py", ledgerPath], {
    cwd: skillDir,
    encoding: "utf8",
  });
}

const CAPS = { max_searches: 18, max_fetches: 12, max_lenses: 10 };

// A healthy run: 8 lenses, distinct anchors, one non-search channel, all-new finds.
const goodLedger = {
  caps: CAPS,
  baseline: { query: "best web search api", finds: [{ name: "Tavily", url: "tavily.com" }] },
  lenses: Array.from({ length: 8 }, (_, i) => ({
    lens: `L${i}`,
    anchor: `anchor${i}`,
    channel: i === 0 ? "github" : "search",
    searches: 2,
    fetches: 1,
    finds: [{ name: `Tool${i}`, url: `t${i}.com` }],
  })),
};

// A collapsed run: too few lenses, both reproduce the baseline, shared anchor, no channel lens.
const collapsedLedger = {
  caps: CAPS,
  baseline: { query: "best web search api", finds: [{ name: "Tavily", url: "tavily.com" }] },
  lenses: [
    { lens: "A", anchor: "same", channel: "search", searches: 2, fetches: 0, finds: [{ name: "Tavily", url: "tavily.com" }] },
    { lens: "B", anchor: "same", channel: "search", searches: 2, fetches: 0, finds: [{ name: "Tavily", url: "https://www.tavily.com/" }] },
  ],
};

describe("tesser-discover/scripts/overlap.py — deterministic discovery gate", () => {
  it("its own Python unit tests pass (run inside the vitest suite)", () => {
    const res = spawnSync("python3", [testOverlapPy], { encoding: "utf8" });
    if (res.error) throw res.error;
    expect(res.status, res.stdout + res.stderr).toBe(0);
    expect(res.stdout).toMatch(/ALL TESTS PASSED/);
  });

  it("bare `scripts/overlap.py` resolves from the skill dir and PASSES a healthy ledger", () => {
    const res = runGate(writeLedger(goodLedger));
    if (res.error) throw res.error;
    expect(res.status, res.stdout + res.stderr).toBe(0);
    expect(res.stdout).toMatch(/RESULT: all gates pass/);
    expect(res.stdout).toMatch(/= 100%/);
  });

  it("FAILS (exit 1) a collapsed / baseline-reproducing ledger", () => {
    const res = runGate(writeLedger(collapsedLedger));
    if (res.error) throw res.error;
    expect(res.status).toBe(1);
    expect(res.stdout).toMatch(/gate\(s\) FAILED/);
    expect(res.stdout).toMatch(/COLLAPSED/);
  });
});
