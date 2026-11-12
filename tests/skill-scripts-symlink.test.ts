// Every tesser skill is a peer directory under the repo — no skill lives at the
// repo root. A skill reaches its scripts in one of TWO ways, and the bare
// `scripts/X` reference in its SKILL.md must resolve from the skill's own base
// dir on every install shape (git clone, GitHub zip, project symlink):
//
//   1. Shared-scripts symlink (tesser-benchmark): a committed
//      `scripts -> ../scripts` symlink, so `scripts/fetch` reaches the repo's
//      shared scripts/ dir.
//   2. Self-contained, real local scripts/ (tesser-discover): a REAL (non-symlink)
//      scripts/ dir holding its own overlap.py — discovery-specific tooling no
//      other skill shares, so `scripts/overlap.py` resolves locally, not to ../scripts.

import { describe, it, expect } from "vitest";
import { spawnSync } from "node:child_process";
import { readlinkSync, statSync, lstatSync, existsSync } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const sharedScripts = path.join(repoRoot, "scripts");

// Category 1: skills that shell out to the SHARED scripts via a `scripts -> ../scripts`
// symlink. tesser-discover (category 2, a real local scripts/ dir) is asserted separately below.
const SCRIPTS_USING_SKILLS = ["tesser-benchmark"];

describe("skill scripts access — committed `scripts -> ../scripts` symlink", () => {
  for (const skill of SCRIPTS_USING_SKILLS) {
    const link = path.join(repoRoot, skill, "scripts");

    it(`${skill}/scripts is a symlink to ../scripts`, () => {
      expect(readlinkSync(link)).toBe("../scripts");
    });

    it(`${skill}/scripts resolves to the shared scripts dir`, () => {
      expect(path.resolve(path.dirname(link), readlinkSync(link))).toBe(sharedScripts);
      // and it actually points at a directory holding the real scripts
      expect(statSync(link).isDirectory()).toBe(true);
      expect(existsSync(path.join(link, "fetch"))).toBe(true);
    });

    it(`bare \`scripts/fetch\` from ${skill}/ reaches the real fetch`, () => {
      // Run with cwd = the skill dir, exactly as the agent does (`cd $BASE && scripts/X`).
      // The real fetch requires a subcommand → argparse usage error, exit 2 naming
      // its subcommands. That proves the symlink resolved.
      const res = spawnSync("python3", ["scripts/fetch"], {
        cwd: path.join(repoRoot, skill),
        encoding: "utf8",
      });
      expect(res.status).toBe(2);
      expect(res.stderr).toMatch(/docs,source,resolve,consult/);
    });
  }

  it("tesser-discover has a REAL local scripts/ dir (not a symlink) holding its own overlap.py", () => {
    const scripts = path.join(repoRoot, "tesser-discover", "scripts");
    expect(existsSync(scripts)).toBe(true);
    // A real directory, NOT a `-> ../scripts` symlink — discovery tooling is not shared.
    expect(statSync(scripts).isDirectory()).toBe(true);
    expect(lstatSync(scripts).isSymbolicLink()).toBe(false);
    expect(existsSync(path.join(scripts, "overlap.py"))).toBe(true);
    // And it does NOT resolve to the shared scripts dir.
    expect(path.resolve(scripts)).not.toBe(sharedScripts);
  });
});
