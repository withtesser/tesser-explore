# tesser-explore

Claude Code skills that help your agent give you more complete and accurate information when you're choosing software to depend on or buy.

- **`/tesser-discover`** searches for options from many angles, so you get more than the common ones the model already knows from training.
- **`/tesser-benchmark`** tells you how a piece of software actually behaves and performs. It reads the source and, where it makes sense, builds it and runs its tests, instead of relying on what the model remembers or what the software's makers claim.

Both are an early alpha.

## Quickstart

Install in your terminal with one command:

```
curl -fsSL https://raw.githubusercontent.com/withtesser/tesser-explore/main/install.sh | bash
```

Then try both skills in one session. Start by finding your options:

```
claude "/tesser-discover My camera's JPEGs have a color look that its raw .dng files lose when I open them in Lightroom. What tools can work out the edits that make a raw file match its JPEG?"
```

You get a report that covers the common options and the ones an obvious search doesn't reach, ranked on the same terms. Then check the top few against their real code, in the same session:

```
/tesser-benchmark let's compare the top three from that report, Image-To-LUT, Deep Preset and NCST, to see how closely each one matches the JPEG and how long it takes per photo
```

It goes to each one's source, builds and runs what it can, and shows you the commands it ran and what came out.

`/tesser-benchmark` also works on its own. Ask about anything: a library you're weighing, one you already ship, an API you're unsure of. You get a grounded, plain-language answer right away, then a background pass over the real source that stays quiet if the answer held up or posts a short correction if it didn't. Add "does it actually work?" and it builds and runs the thing to check. The installer prints one such question to start with.

**Rather read before you run?** Download and inspect the installer first:

```
curl -fsSL https://raw.githubusercontent.com/withtesser/tesser-explore/main/install.sh -o tesser-install.sh
less tesser-install.sh && bash tesser-install.sh
```

**Rather install by hand?** The installer is just these two steps:

```
git clone https://github.com/withtesser/tesser-explore ~/.claude/skills/tesser
~/.claude/skills/tesser/scripts/setup
```

Setup links the two skills and creates a private Python environment at `~/.tesser/venv`. Nothing touches your system Python.

## /tesser-discover

Ask an agent which tools you should consider and it names the ones it knows from training, then runs the obvious search and gets the same names back. `/tesser-discover` is for when you're choosing a dependency or a product and want to see the options that answer leaves out.

- **Comes at the question from many directions before it searches.** It first lists eight to ten different ways into the question: the words a product uses for itself, a neighboring field that solves the same problem under another name, the places new projects announce before they rank. Each one has to search for something different, and at least one has to look somewhere other than plain web search.
- **Compares against the obvious search.** It also runs the single most obvious query and records what that returns. The report covers both sides, the common options and the ones only the wider search found, and ranks them on the same criteria. If a common option is the best one, it says so.
- **Counts its results with a script.** Every run records what each search found and runs a script over that record. The script reports how much of what it found the obvious query missed, whether two of its searches were really the same search, and whether the run stayed within its limits. It checks a record the agent wrote, so it catches sloppiness, not fabrication.
- **Stays small.** One agent does all of it, with no subagents: at most 18 searches and 12 page fetches a run.
- **Reads Reddit and forums if you give it an OpenAI key.** Claude Code's built-in search can't read Reddit, so those searches go through OpenAI's web search. That needs `OPENAI_API_KEY` in your environment and is billed to your OpenAI account. Without a key, the report says Reddit wasn't searched.

## /tesser-benchmark

You know how your coding agent will confidently explain how some library works, and you can't tell whether it actually knows or it's guessing, so you end up double-checking it yourself? `/tesser-benchmark` is built for exactly that moment. Instead of trusting docs or its own memory, it goes to the real code, reading it and, when the question calls for it, building and running it.

- **Answers first, in plain language.** You get the answer immediately, with a clear sense of how it knows each part: whether it ran the code, read it, is going by the project's README, or is recalling from memory.
- **Checks the answer against the real source, in the background.** It works from one specific commit and backs its load-bearing claims with the exact file and line. If reading the source changes the answer, a follow-up corrects it; if the source confirms it, it stays quiet. An answer it already gave you is never silently edited.
- **Scales the work to the question.** An overview reads the README and the few files that matter. "How do I set it up" adds a quick build to confirm it installs. "Does it actually work" runs it end to end with no credentials needed: a runnable binary if there is one, else the test suite, else a minimal example. Either way it shows you the commands it ran and whether they passed, not a verdict that the library is objectively correct.
- **Pins and reuses.** The first time it reads a library, it locks onto one specific commit and reuses that from then on. It never quietly jumps to a newer version, and only moves forward when you ask.
- **Knows its limits and says so.** When a library caps how far it can go, say a closed hosted service it can describe but not run, it tells you up front what it can confirm versus only describe.

### Saved results

The first time `/tesser-benchmark` answers a question by going to a library's source, it can save what it found: the repo, the exact commit, and every command it ran. The next time you ask about that library, it reads that saved result instead of cloning again. No saved results ship with tesser-explore, so your first question about any library always goes to the source.

These are ordinary local files, and `/tesser-benchmark` doesn't re-verify them before reuse, so anything that can write to `~/.tesser/` can change what a saved result says.

### Untrusted code

`/tesser-benchmark` clones and builds the open-source code you ask about, on your machine. Claude Code's normal permissions apply; the skill adds no confirmation layer of its own.

## Self-update

The install updates itself each time `/tesser-benchmark` runs, with a quick `git pull` that brings both skills up to date. If it can't, because you're offline or you've made local changes, it skips silently and never blocks an answer. `/tesser-discover` doesn't pull on its own. To opt out, delete the `.git` directory in `~/.claude/skills/tesser`.

## Local state

`/tesser-benchmark` keeps everything it saves under `~/.tesser/`: a log of what you asked and what it looked at, the repos it has cloned, and saved results from past runs. The private Python environment is there too. It all stays on your machine.

`/tesser-discover` saves nothing under `~/.tesser/`. If you use an OpenAI key, each call's token and search counts are appended to `~/.local/state/openai-usage/calls.jsonl`.

## Development

The skills need only `git` and `python3`. The test suite also needs Node.js:

```
npm ci
npm test
```

`npm test` first creates `.venv/` in the repo and installs `requirements.txt` (PyYAML) into it, then runs the suite with that Python first on `PATH`. Four end-to-end tests drive a real Claude Code session and are skipped unless `RUN_E2E=1` is set.

## License

MIT. See [LICENSE](LICENSE).
