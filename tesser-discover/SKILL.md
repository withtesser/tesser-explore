---
name: tesser-discover
description: "Map a space — the mainstream options and the obscure, non-obvious entrants a plain agent session and a normal web search miss (tools, products, papers, companies, repos) — and recommend across both on the same terms. Beats WebSearch ranking bias and keyword-collision by deriving many independent search \"lenses\" first, then searching each, including Reddit and forums through OpenAI's web search. Use when you want to map the long tail of a space (\"what are all the X out there\", \"find lesser-known Y\", \"what's the landscape of Z beyond the famous names\"), or to find a better tool/stack for a job. Not for grounding a single known dependency (that's /tesser-benchmark) and not for a deep-research fan-out (this runs cheap and inline)."
allowed-tools: WebSearch, WebFetch, Bash, Write, Read
---

# tesser-discover

You find the **obscure tail** of a space — the entrants a normal search buries — without already knowing their names. The method (frame-walk) is an anti-anchoring trick: don't search synonyms of the topic; first derive many *independent vantage points* ("lenses"), then search each, because a single keyword query can only mine one neighborhood.

The companion to tesser's grounding: **tesser-benchmark answers a question about a dependency you already have; tesser-discover surfaces the ones you don't.** It shares tesser's north star — beat what a plain vanilla agent session would surface. A default session, asked "what's the landscape of X", pattern-matches to the famous names it already holds; this skill's whole job is to find what that reflex misses. The find happens when a query you generate lands on the exact words a buried entrant uses to describe *itself* — so the game is generating enough genuinely different vocabularies that one collides.

**Discovery is how you reach the tail, not a filter on what you report.** The user wants the best option for their job whichever side it's on, so the report covers the mainstream too (what the obvious search and the well-known names give) and ranks everything on the same criteria. A mainstream winner reported as the winner is a correct result; a tail-only report that drops it is not.

## Contract

What this skill guarantees, and what it forbids. These are gates, not suggestions — `scripts/overlap.py` enforces the measurable ones.

**Cost — runs inline, bounded, never fanned out.** A prior version of this work ran as a ~107-agent deep-research fan-out and **burned ~$100 in one run**. The fan-out is not where the value is; lens *diversity* is. So you run the entire thing **as yourself, the single current agent**, using only the cheap built-in tools:
- **No `/deep-research`, no subagents, no Workflow, no `Agent`/`Task` fan-out.** You do the searching directly. (The `allowed-tools` list above already excludes them — the prose is belt-and-suspenders.)
- **≤ 2 searches per lens**, **≤ 18 searches total**, **≤ 12 `WebFetch` total** (fetch only to confirm a specific fact about a promising hit, never to read around). A call to `scripts/openai_websearch.py` counts as one search against these caps; log it as `openai_calls`, and log the `searches:` number from its receipt as `openai_searches`, because one call runs many searches inside it and the cost receipt has to show that.
- **≤ 10 lenses.** This closes the "invent more lenses to buy more searches" loophole — the per-lens cap alone is gameable.
- A full run costs a couple of dollars. If you feel the urge to spawn agents to "cover more ground," that urge is the bug — sharpen a lens, don't add an agent.

**Verdict is computed, not claimed.** The skill's entire value is *non-overlap with the obvious-keyword baseline*. That metric, cross-lens dedup, and lens-independence are pure set operations — so you do **not** assert them from memory. Every run ends by writing a ledger and running `scripts/overlap.py`, whose gates are authoritative. If it reports a FAIL, the run is not shippable: fix the cause (a genuinely new lens, not a reworded one) and rerun.

**The ledger runs on retrieved evidence, not curated names** — this is the only real defense against self-deception, because the script can only check what you feed it. So: each find's `url` must be an **actual result URL a search returned**, not a name you recalled; and the `baseline.finds` must be the **verbatim top results of the single obvious query** (paste them as returned), never a hand-picked list — a stacked baseline fakes the non-overlap. Honest limit: the script audits a ledger *you* wrote, so it catches sloppiness and accidental anchoring, not deliberate fabrication. Its job is to keep an honest agent honest, and it does that well.

## Inputs

- **Target** (required) — the space to map. If the user didn't name one, ask one short question to get it.
- **Fit bar** (optional) — what counts as a hit / what's disqualified. Default: include low-visibility, pre-product, niche entrants (flag confidence) and the household names too, each labeled mainstream or tail.
- **"Better than" axis** (optional) — when the target is "a better X", the specific weaknesses each candidate is judged against (see the worked example).

Invoked bare with no target → default to the **better-search-tools** example at the bottom; it is the canonical instantiation.

## Stage 1 — derive the lenses (with a distinctness gate), BEFORE searching

Generate **8–10 lenses**. A lens is a vantage point that surfaces a *different population* of results than the obvious keyword query. For each, declare:

- **label** — short name.
- **anchor** — its primary query noun. **No two lenses may share an anchor** (overlap.py fails the run if they do). This is what stops eight rewordings of the same term.
- **channel** — where it searches: `search` (plain web), or a non-search surface — `show-hn`, `arxiv`, `github` (created-recently), `accelerator`, `newsletter`, `snowball` (who the known players cite/fund/follow), `community` (Reddit and forums). **At least one lens must be a non-search channel** (gated) — this is the method's known blind spot, so it's forced.

**Always include one `community` lens**: what practitioners report using, recommending and abandoning. Run it through `scripts/openai_websearch.py "<instruction naming Reddit and the time window>"` (with `run_in_background` or a 600000 ms timeout; a call takes minutes), because WebSearch refuses reddit.com and Reddit refuses scripted requests. Practitioner reports are the evidence users ask for most, so it's the default. If the helper exits non-zero (no key, out of credits), mark the lens `"unreachable": "<the helper's message>"` in the ledger and say so plainly at the top of the report; it doesn't count toward the lens minimum, so replace it with another lens.
- **territory note** — one line: what this reaches that a plain keyword search cannot.

Rules:
- **Derive lenses from the nature of the problem**, not a category list you've seen.
- The illustration that *defines* "lens" (an unrelated problem, so it's not a hint): to name the verb for "turn a seed into a finished thing," searching synonyms of *translate* dead-ends — every result is translate-adjacent. Asking ~25 unrelated domains "what is this called in *your* world?" (cooking, metalwork, biology, agriculture, physics…) breaks the anchor and surfaces words synonyms can't reach. Make that move.
- Lens families that tend to be independent (a prompt, not a checklist — derive your own): the target's own *distinctive self-description* vocabulary; adjacent fields that solve the same problem-shape under a different name; the *channel* where new entrants announce before they rank; who the known players cite/fund/follow (snowball 2–3 hops); the *contrarian* framing that rejects the mainstream approach; the non-English / non-US toolchain.

Show the lens table before searching.

## Stage 2 — search each lens, baseline, then compute the verdict

1. Search each lens independently (≤2 `WebSearch` each, ~2 result-pages deep). Record which lens surfaced each entry and the exact query.
2. Run the **single most obvious keyword query** as a labeled **baseline**. Record its result URLs verbatim (`baseline.finds`), and the products or tools those results name (`baseline.entrants`, each with the result URL that named it). The entrants are the mainstream: they are the report's mainstream section, and they're what the non-overlap score compares against, so a baseline of listicles doesn't make every find look new.
3. When a relevant page blocks fetch (Cloudflare / anti-bot / JS), try a cache or third-party mention via one `WebFetch` rather than skipping — respect the fetch budget.
4. **Write the ledger** to a temp JSON file (schema in `scripts/overlap.py`'s header): `caps` (`max_searches` 18, `max_searches_per_lens` 2, `max_fetches` 12, `max_lenses` 10), `baseline.finds` (verbatim top results of the obvious query) and `baseline.entrants`, and per-lens `anchor`/`channel`/`searches`/`openai_calls`/`openai_searches`/`fetches`/`finds` (each find = `name` + the **actual result `url`**). A lens with no finds carries `null_reason` (searched, nothing relevant) or `unreachable` (the source couldn't be reached); a silent empty lens fails the run.
5. **Run it:** `python3 scripts/overlap.py <ledger.json>`. It computes the deduped find set, the **non-overlap %**, collapsed lens-pairs, duplicate **and near-synonym** anchors, channel coverage, per-lens + total budget, and flags empty lenses / same-name-different-URL dupes. Treat its output as the source of truth for those numbers — quote them, don't recompute by eye.
6. If it FAILs, the run mostly reproduced the baseline or the lenses collapsed (or near-synonym anchors mean you anchored). **Fix and rerun** — replace the offending lens with a genuinely independent one; never widen the budget to compensate, never pad.

## Output Format

A short report:

0. **Anything that didn't run** — first, in one line each: an unreachable lens and why (e.g. "Reddit not reached: OpenAI account out of credits").
1. **The lenses** — the table (label / anchor / channel / territory note), so the method is auditable.
2. **The mainstream** — the baseline's entrants, one line each: what it is and how it fits the job. Check them as you would a tail find; being famous isn't evidence of fit, and neither is being obscure.
3. **The finds** — one block per *new-vs-baseline* entry (the script's `+` list):
   - name + who's behind it (org/people)
   - one line: what it is
   - primary source URL (repo / arXiv / official docs) — say explicitly if only secondary exists
   - approx first-release + latest-update date
   - **which lens surfaced it**, and the exact query
   - findability note: why it was buried
   - *(with a "better than" axis: which weakness(es) it fixes; for tools, MCP/CLI + how it wires in + pricing)*
   - flag any self-reported "best/fastest" claim
4. **Recommendation across both** — rank mainstream and tail candidates together on the job's criteria (the "better than" axis when given), each labeled mainstream or tail, with the evidence for its rank.
5. **The ledger verdict** — paste overlap.py's non-overlap %, budget line (including the searches OpenAI ran inside its calls), and any gate flags. This is the run's receipt. OpenAI calls are billed to the user's API credits, unlike the rest of the run: give their dollar cost too, from the usage log the helper writes (each call's tokens by kind and search count, priced at OpenAI's published rates; a cost tool such as token-cost's `openai` mode does this).
6. **Could-not-verify** — gaps reported honestly, never padded.

Be skeptical, not promotional. Date everything. Prefer official docs/repos over blogs. Offer to `Write` the report to a file if the user wants it durable; don't write unprompted.

## Anti-Patterns

- **Anchoring** — eight rewordings of the obvious term instead of eight independent vantage points. The shared-anchor gate exists to catch exactly this; if overlap.py reports a collapsed pair, you anchored.
- **Fan-out** — spawning agents/subagents/workflows to "search more." Forbidden (see Contract). Sharpen a lens, don't add an agent.
- **Deep-research escalation** — letting the task balloon into `/deep-research`.
- **Claiming non-overlap by eye** — the whole point is a *computed* verdict; if you didn't run overlap.py, you didn't finish.
- **Padding** — inventing weak entries so a lens "produced something." A lens that yields nothing is a finding; report it.
- **Reproducing the baseline** — a find set that overlaps the obvious query is a null result, regardless of count.
- **Coinage-only targets are unreachable cold** — an entrant whose name is namesake-buried *and* whose only distinctive handles are private coinages no stranger would type is structurally undiscoverable by any method. If the target is one such specific entity, say so rather than burning the budget; cold discovery reaches entities whose distinctive vocabulary is *shared* across a domain, not ones reachable only by their own invented terms.

---

## Worked example (and the bare-invocation default): better search tools

The canonical instantiation — give a Claude Code agent better search than the built-in WebSearch.

**Target:** add-on tools / MCP servers that beat the built-in WebSearch.

**"Better than" axis** — assess each candidate on which built-in weakness it fixes:
- **Index/engine** — built-in is *not* Google-backed and has real coverage gaps (misses new, low-authority, niche sites). Which index does the candidate use; does it reach Google-grade coverage?
- **Region** (built-in is US-only), **freshness**, and result **depth** (built-in returns titles/snippets, not full page content).
- **Ranking** on low-authority or **namesake-buried** sites.
- **Walled/JS content** — can it retrieve behind Cloudflare/anti-bot or JS-rendered pages? (the built-in's fetch 403s on these.)

**Per-entry, additionally capture:** is there an MCP server (official/community) and/or a CLI an agent can call (link it); how it wires into Claude Code (MCP config, auth/API key, sandbox needs); pricing / free tier / rate limits; maturity (GA vs beta).

**Deliver, beyond the standard output:** a recommended **stack** — which 2–4 tools together give the biggest jump over the built-in, mapped to the weaknesses above.

> Provenance: frame-walk is the "vocabulary-collision-distance" method — derive independent vantage points so one query collides with a buried entrant's own self-description. This skill was re-homed into tesser from a standalone research skill.
