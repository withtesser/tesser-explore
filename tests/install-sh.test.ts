// Structural gates for install.sh — the terminal installer.
//
// install.sh runs in the USER's shell (curl … | bash), not via an agent, so it
// sidesteps the auto-mode "Untrusted Code Integration" denial that blocks an
// agent from cloning into ~/.claude/skills/. These gates pin the load-bearing
// shape without hitting the network: syntax validity, and that it still clones
// the real repo, runs setup with the session-notice suppressed, and hands back
// a copy-paste claude command. A regression that dropped any of these would
// silently break onboarding.

import { describe, it, expect } from "vitest";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const installSh = path.join(repoRoot, "install.sh");
const src = fs.readFileSync(installSh, "utf8");

describe("install.sh (terminal installer)", () => {
  it("exists and is executable", () => {
    expect(fs.existsSync(installSh)).toBe(true);
    // owner-execute bit set
    expect(fs.statSync(installSh).mode & 0o100).toBeTruthy();
  });

  it("is valid bash (bash -n)", () => {
    const res = spawnSync("bash", ["-n", installSh], { encoding: "utf8" });
    expect(res.status, res.stderr).toBe(0);
  });

  it("clones the real repo into the documented personal-install location", () => {
    expect(src).toContain("github.com/withtesser/tesser-explore");
    expect(src).toContain(".claude/skills/tesser");
    expect(src).toMatch(/git clone/);
  });

  it("runs scripts/setup with the session-restart notice suppressed", () => {
    // The venv + skill linking is setup's job — install.sh must delegate, not
    // re-implement — and it must mute the in-session restart notice (wrong for a
    // terminal install that launches a fresh session).
    expect(src).toMatch(/scripts\/setup/);
    expect(src).toContain("TESSER_SUPPRESS_SESSION_NOTICE=1");
  });

  it("hands back a copy-paste claude command for the first example", () => {
    // The example is a /tesser-benchmark slash command (reliable invocation),
    // emitted as `claude "$EXAMPLE"` in the closing message.
    expect(src).toMatch(/EXAMPLE="\/tesser-benchmark/);
    expect(src).toMatch(/claude "\$EXAMPLE"/);
  });
});
