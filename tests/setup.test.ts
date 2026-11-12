// Type-C deterministic gates for scripts/setup (T12, D32).
//
// scripts/setup creates <TESSER_HOME>/venv and installs requirements.txt
// into it, idempotent on the requirements hash. The gates run sequentially
// against ONE temp home: a real venv is created once (the only step that
// talks to pip's index/cache), then the no-op and reinstall behaviors are
// proven hermetically by swapping the venv's pip for a recording shim — if
// setup invokes pip when it should not, the shim's record file betrays it.

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const setupScript = path.join(repoRoot, "scripts", "setup");
const requirements = path.join(repoRoot, "requirements.txt");

let home: string;
let skillsDir: string; // TESSER_SKILLS_DIR: isolate companion-symlink creation from the real ~/.claude/skills

const reqHash = () =>
  crypto.createHash("sha256").update(fs.readFileSync(requirements)).digest("hex");

function runSetup() {
  const res = spawnSync(setupScript, [], {
    encoding: "utf8",
    env: { ...process.env, TESSER_HOME: home, TESSER_SKILLS_DIR: skillsDir },
  });
  if (res.error) throw res.error;
  return res;
}

beforeAll(() => {
  home = fs.mkdtempSync(path.join(os.tmpdir(), "tesser-setup-test-"));
  skillsDir = path.join(home, "skills");
});

afterAll(() => {
  fs.rmSync(home, { recursive: true, force: true });
});

describe("scripts/setup (D32)", () => {
  const venv = () => path.join(home, "venv");
  const stampPath = () => path.join(venv(), ".requirements-sha256");
  const pipPath = () => path.join(venv(), "bin", "pip");
  const recordPath = () => path.join(home, "pip-record");

  it(
    "fresh home: creates the venv, installs requirements, stamps the hash",
    () => {
      const res = runSetup();
      expect(res.status, res.stderr).toBe(0);

      const venvPython = path.join(venv(), "bin", "python3");
      expect(fs.existsSync(venvPython)).toBe(true);

      // The venv's python can import yaml — the validator's dependency is in.
      const imp = spawnSync(venvPython, ["-c", "import yaml"], {
        encoding: "utf8",
      });
      expect(imp.status, imp.stderr).toBe(0);

      // Stamp == sha256 of requirements.txt (the idempotence key).
      expect(fs.readFileSync(stampPath(), "utf8").trim()).toBe(reqHash());
    },
    180_000,
  );

  it("re-run with unchanged requirements is a no-op: pip never runs", () => {
    // Swap the venv's pip for a recording shim; a no-op must not touch it.
    fs.writeFileSync(
      pipPath(),
      `#!/bin/sh\nprintf '%s\\n' "$*" > "${recordPath()}"\nexit 0\n`,
      { mode: 0o755 },
    );
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0);
    expect(res.stdout).toMatch(/up to date/);
    expect(fs.existsSync(recordPath())).toBe(false);
  });

  it("requirements-hash change triggers a reinstall and restamps", () => {
    // Simulate a changed requirements.txt by corrupting the stamp — the
    // comparison is stamp == sha256(requirements.txt) either way.
    fs.writeFileSync(stampPath(), "0".repeat(64) + "\n");
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0);
    // The shim recorded an install call against requirements.txt …
    const recorded = fs.readFileSync(recordPath(), "utf8");
    expect(recorded).toMatch(/install/);
    expect(recorded).toContain("requirements.txt");
    // … the venv was NOT recreated (our shim survived) …
    expect(fs.readFileSync(pipPath(), "utf8")).toContain(recordPath());
    // … and the stamp is back to the true hash.
    expect(fs.readFileSync(stampPath(), "utf8").trim()).toBe(reqHash());
  });

  it("a failed pip install exits 1 and leaves the venv UNSTAMPED so the next run retries", () => {
    // The load-bearing guarantee: the stamp is written only after a
    // successful install. A regression that stamps despite failure would
    // turn every later setup into a no-op against a broken venv.
    const corrupt = "0".repeat(64);
    fs.writeFileSync(stampPath(), corrupt + "\n");
    fs.writeFileSync(pipPath(), "#!/bin/sh\nexit 1\n", { mode: 0o755 });
    const res = runSetup();
    expect(res.status).toBe(1);
    expect(res.stderr).toMatch(/pip install failed/);
    // Stamp NOT advanced to the true hash — the next run will retry.
    expect(fs.readFileSync(stampPath(), "utf8").trim()).toBe(corrupt);
  });

  // Distribution: Claude Code discovers skills only one level deep, so every
  // skill in this repo must be symlinked up as a top-level peer — no skill lives
  // at the repo root. Both are linked the same way (uniform install); the
  // core skill is not privileged. Pin it so it can't silently regress.
  it("links every skill into the skills dir (uniform peers, symlink, self-correcting)", () => {
    // The prior test left a failing (exit-1) pip shim; restore a healthy venv so
    // setup reaches the link step, then assert the links.
    fs.writeFileSync(pipPath(), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
    fs.writeFileSync(stampPath(), reqHash() + "\n");
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0);
    for (const name of ["tesser-benchmark", "tesser-discover"]) {
      const link = path.join(skillsDir, name);
      expect(fs.existsSync(link), `${name} link missing`).toBe(true);
      expect(fs.lstatSync(link).isSymbolicLink(), `${name} is not a symlink`).toBe(true);
      expect(fs.realpathSync(link)).toBe(fs.realpathSync(path.join(repoRoot, name)));
    }
  });

  it("does not clobber a real directory sitting where a companion link would go", () => {
    const collide = path.join(skillsDir, "tesser-discover");
    fs.rmSync(collide, { recursive: true, force: true });
    fs.mkdirSync(collide, { recursive: true }); // a real dir, not our symlink
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0); // linking is best-effort, never fails setup
    expect(res.stderr).toMatch(/is not our symlink/);
    expect(fs.lstatSync(collide).isSymbolicLink()).toBe(false); // left untouched
  });

  // A skill installed into a ~/.claude/skills/ that did not exist at session
  // start is not hot-loaded until the session restarts. setup can't see session
  // start, so it uses "am I the only skill here?" as the proxy: only tesser's
  // own skills present -> first-ever-skill install -> tell the developer to
  // stop and resume. (install.sh sets TESSER_SUPPRESS_SESSION_NOTICE to mute it,
  // since a terminal install launches a fresh session that sees the skills.)
  it("first-skill install (only tesser's own skills present) prints the restart notice", () => {
    // By now skillsDir holds only tesser's own set (the linked companions +
    // the tesser-discover real dir from the prior test), nothing foreign.
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0);
    expect(res.stdout).toMatch(/FIRST-SKILL INSTALL/);
    expect(res.stdout).toMatch(/Stop this Claude Code session/);
  });

  it("TESSER_SUPPRESS_SESSION_NOTICE mutes the restart notice (install.sh path)", () => {
    // Same first-skill state as the test above (only tesser's own skills), so
    // the notice WOULD fire — the env var is the only thing suppressing it.
    const res = spawnSync(setupScript, [], {
      encoding: "utf8",
      env: { ...process.env, TESSER_HOME: home, TESSER_SKILLS_DIR: skillsDir, TESSER_SUPPRESS_SESSION_NOTICE: "1" },
    });
    expect(res.status, res.stderr).toBe(0);
    expect(res.stdout).not.toMatch(/FIRST-SKILL INSTALL/);
  });

  it("stays silent when another (non-tesser) skill is already present", () => {
    // A pre-existing foreign skill means the skills dir was already watched —
    // no restart needed, so no notice.
    const other = path.join(skillsDir, "some-other-skill");
    fs.mkdirSync(other, { recursive: true });
    fs.writeFileSync(path.join(other, "SKILL.md"), "---\nname: some-other-skill\n---\n");
    const res = runSetup();
    expect(res.status, res.stderr).toBe(0);
    expect(res.stdout).not.toMatch(/FIRST-SKILL INSTALL/);
  });
});
