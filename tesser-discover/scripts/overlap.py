#!/usr/bin/env python3
"""
overlap.py — the deterministic core of frame-walk-discovery.

The skill's whole value is NON-OVERLAP with the obvious-keyword baseline. That
metric, plus cross-lens dedup and lens-distinctness, are pure set operations on
name/URL lists — so they must NOT live in the agent's head. The agent gathers
finds per lens (the latent work); this script computes the verdict (the
deterministic work) and constrains what the agent is allowed to claim.

Usage:
    python3 overlap.py <ledger.json>

Ledger schema (the agent writes this after Stage 2):
{
  "caps": {"max_searches": 18, "max_fetches": 12, "max_lenses": 10},
  "baseline": {"query": "...", "finds": [{"name": "...", "url": "..."}, ...],
               "entrants": [{"name": "...", "url": "<the baseline result that named it>"}, ...]},
  "lenses": [
    {"lens": "short label", "anchor": "primary query noun",
     "channel": "search|show-hn|arxiv|github|accelerator|newsletter|snowball|community|...",
     "searches": 2, "fetches": 1,
     "openai_calls": 0, "openai_searches": 0,
     "finds": [{"name": "...", "url": "..."}, ...]},
    ...
  ]
}

baseline.finds are the obvious query's result URLs, verbatim. baseline.entrants are
the products/tools those results name (the mainstream). A lens find counts as
already-in-baseline when its URL matches a baseline URL or its name matches a
baseline entrant, so a baseline of listicles no longer makes every find look new.

A lens with no finds must say why: "null_reason" (searched, nothing relevant: a
finding) or "unreachable" (the source couldn't be reached: e.g. the OpenAI helper's
error). An unreachable lens doesn't count toward the lens minimum or the channel gate.

openai_calls count against the search caps like WebSearch calls; openai_searches is
the number of searches OpenAI ran inside those calls (the helper's receipt), reported
so the cost receipt isn't understated.

Exit code 0 = all gates pass; 1 = at least one gate FAILED (the run is not
shippable as-is). Everything is reported either way.
"""
import json
import re
import sys
from collections import defaultdict

# Tunable gate thresholds (kept here so the rule is auditable, not in prose).
NON_OVERLAP_FLOOR = 0.40      # < this share new-vs-baseline => the run mostly reproduced the obvious query
LENS_COLLAPSE_SHARE = 0.60    # two lenses sharing >= this share of finds are "collapsed" (not independent)
MIN_LENSES = 8


def canon_url(url):
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("#")[0].split("?")[0]
    u = u.rstrip("/")
    return u


def canon_name(name):
    if not name:
        return ""
    n = name.strip().lower()
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def key(find):
    """Identity of a find: canonical URL if present, else canonical name."""
    cu = canon_url(find.get("url", ""))
    return cu if cu else "name:" + canon_name(find.get("name", ""))


def main():
    if len(sys.argv) != 2:
        print("usage: python3 overlap.py <ledger.json>", file=sys.stderr)
        return 2
    with open(sys.argv[1]) as f:
        led = json.load(f)

    caps = led.get("caps", {})
    max_searches = caps.get("max_searches", 18)
    max_fetches = caps.get("max_fetches", 12)
    max_lenses = caps.get("max_lenses", 10)
    max_per_lens = caps.get("max_searches_per_lens", 2)

    baseline = led.get("baseline", {})
    base_keys = {key(x) for x in baseline.get("finds", [])}
    entrants = baseline.get("entrants", [])
    base_names = {canon_name(x.get("name", "")) for x in baseline.get("finds", []) + entrants} - {""}
    all_lenses = led.get("lenses", [])
    unreachable = [(ln.get("lens", f"lens{i}"), ln.get("unreachable"))
                   for i, ln in enumerate(all_lenses) if ln.get("unreachable")]
    lenses = [ln for ln in all_lenses if not ln.get("unreachable")]

    # Per-lens find-key sets + global dedup (which lenses surfaced each find).
    lens_keys = []
    surfaced_by = defaultdict(set)
    name_of = {}
    for i, ln in enumerate(lenses):
        ks = set()
        for fnd in ln.get("finds", []):
            k = key(fnd)
            ks.add(k)
            surfaced_by[k].add(ln.get("lens", f"lens{i}"))
            name_of.setdefault(k, fnd.get("name", "") or fnd.get("url", ""))
        lens_keys.append(ks)

    # A find is mainstream if its URL is a baseline result or its name is a baseline entrant.
    name_key = {}
    for ln in lenses:
        for fnd in ln.get("finds", []):
            name_key[key(fnd)] = canon_name(fnd.get("name", ""))
    all_keys = set(surfaced_by)
    in_base = {k for k in all_keys if k in base_keys or name_key.get(k) in base_names}
    new_keys = all_keys - in_base
    non_overlap = (len(new_keys) / len(all_keys)) if all_keys else 0.0

    def calls(ln):
        return ln.get("searches", 0) + ln.get("openai_calls", 0)

    total_searches = sum(calls(ln) for ln in all_lenses) + (1 if baseline else 0)
    total_fetches = sum(ln.get("fetches", 0) for ln in all_lenses)
    openai_calls = sum(ln.get("openai_calls", 0) for ln in all_lenses)
    openai_searches = sum(ln.get("openai_searches", 0) for ln in all_lenses)

    # Pairwise lens-collapse detection (Jaccard-style share over the smaller set).
    collapsed = []
    for i in range(len(lenses)):
        for j in range(i + 1, len(lenses)):
            a, b = lens_keys[i], lens_keys[j]
            if not a or not b:
                continue
            inter = len(a & b)
            share = inter / min(len(a), len(b))
            if share >= LENS_COLLAPSE_SHARE:
                collapsed.append((lenses[i].get("lens", f"lens{i}"),
                                  lenses[j].get("lens", f"lens{j}"), round(share, 2)))

    # Distinct anchors / channels (independence by construction).
    anchors = [canon_name(ln.get("anchor", "")) for ln in lenses]
    dup_anchors = sorted({a for a in anchors if a and anchors.count(a) > 1})

    # Near-synonym anchors: catch "search ranking bias" vs "search ranking skew"
    # (literal-string dup-check misses these). Two anchors sharing >=2 significant
    # tokens are flagged as not-independent. Conservative threshold to avoid
    # false-failing genuinely distinct lenses that share one common word.
    STOP = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "vs",
            "based", "using", "with", "by", "as", "is", "are"}

    def sig_tokens(raw):
        toks = re.split(r"[^a-z0-9]+", (raw or "").lower())
        return {t for t in toks if len(t) > 2 and t not in STOP}

    raw_anchors = [(ln.get("lens", f"lens{i}"), sig_tokens(ln.get("anchor", "")))
                   for i, ln in enumerate(lenses)]
    near_synonym = []
    for i in range(len(raw_anchors)):
        for j in range(i + 1, len(raw_anchors)):
            shared = raw_anchors[i][1] & raw_anchors[j][1]
            if len(shared) >= 2:
                near_synonym.append((raw_anchors[i][0], raw_anchors[j][0], sorted(shared)))
    channels = {ln.get("channel", "") for ln in lenses if ln.get("channel")}
    has_channel_lens = bool(channels - {"search", ""})

    # Per-lens search-cap overruns (the Contract promises <= max_per_lens each).
    over_lenses = [(ln.get("lens", f"lens{i}"), calls(ln))
                   for i, ln in enumerate(all_lenses) if calls(ln) > max_per_lens]
    # A null lens is a finding, but it has to say so; a silent empty lens may be a dead source.
    empty_lenses = [(ln.get("lens", f"lens{i}"), ln.get("null_reason"))
                    for i, ln in enumerate(lenses) if not ln.get("finds")]
    silent_empty = [name for name, why in empty_lenses if not why]
    # Soft: same entrant name under different URLs (possible missed dedup).
    name_urls = defaultdict(set)
    for ln in lenses:
        for fnd in ln.get("finds", []):
            cn = canon_name(fnd.get("name", ""))
            cu = canon_url(fnd.get("url", ""))
            if cn and cu:
                name_urls[cn].add(cu)
    same_name_diff_url = sorted(n for n, us in name_urls.items() if len(us) > 1)

    # --- Gates ---
    gates = []
    gates.append(("lens_count >= %d" % MIN_LENSES, len(lenses) >= MIN_LENSES))
    gates.append(("lens_count <= %d (no inflation)" % max_lenses, len(lenses) <= max_lenses))
    gates.append(("total_searches <= %d" % max_searches, total_searches <= max_searches))
    gates.append(("<= %d searches per lens" % max_per_lens, not over_lenses))
    gates.append(("total_fetches <= %d" % max_fetches, total_fetches <= max_fetches))
    gates.append(("non_overlap >= %.0f%%" % (NON_OVERLAP_FLOOR * 100), non_overlap >= NON_OVERLAP_FLOOR))
    gates.append(("no collapsed lens-pairs", not collapsed))
    gates.append(("distinct anchors per lens", not dup_anchors))
    gates.append(("no near-synonym anchor pairs", not near_synonym))
    gates.append((">=1 non-search channel lens", has_channel_lens))
    gates.append(("every empty lens gives a null_reason or is marked unreachable", not silent_empty))

    failed = [g for g, ok in gates if not ok]

    # --- Report ---
    print("FRAME-WALK OVERLAP LEDGER")
    print("=" * 52)
    print(f"lenses: {len(lenses)} reached, {len(unreachable)} unreachable   distinct finds: {len(all_keys)}   "
          f"baseline results: {len(base_keys)}, mainstream entrants named: {len(entrants)}")
    print(f"searches: {total_searches}/{max_searches} (incl. {openai_calls} OpenAI calls that ran "
          f"{openai_searches} searches inside them)   fetches: {total_fetches}/{max_fetches}")
    print(f"NON-OVERLAP vs baseline: {len(new_keys)}/{len(all_keys)} = {non_overlap:.0%}")
    if not entrants:
        print("  (no baseline entrants listed: compared by URL only, so this % is likely inflated)")
    if unreachable:
        print("\nUNREACHABLE lenses (not counted; say so in the report):")
        for name, why in unreachable:
            print(f"  x {name}: {why}")
    if entrants:
        print("\nMainstream entrants (from the baseline results):")
        for e in entrants:
            print(f"  - {e.get('name')}   {e.get('url', '')}")
    print()
    print("New-vs-baseline finds (the actual yield):")
    for k in sorted(new_keys):
        who = ", ".join(sorted(surfaced_by[k]))
        print(f"  + {name_of[k]}   [{who}]")
    seen_in_baseline = in_base
    if seen_in_baseline:
        print(f"\nAlready in baseline (no credit): {len(seen_in_baseline)}")
        for k in sorted(seen_in_baseline):
            print(f"  = {name_of[k]}")
    if collapsed:
        print("\nCOLLAPSED lens-pairs (not independent):")
        for a, b, s in collapsed:
            print(f"  ! {a}  <->  {b}   share={s}")
    if dup_anchors:
        print(f"\nDuplicate anchors (lenses share a primary noun): {dup_anchors}")
    if near_synonym:
        print("\nNEAR-SYNONYM anchors (>=2 shared significant tokens — not independent):")
        for a, b, sh in near_synonym:
            print(f"  ! {a}  <->  {b}   shared={sh}")
    if over_lenses:
        print(f"\nLenses over the per-lens search cap ({max_per_lens}): {over_lenses}")
    if empty_lenses:
        print("\nEmpty lenses (0 finds):")
        for name, why in empty_lenses:
            print(f"  {'-' if why else '!'} {name}: {why or 'NO null_reason given (dead source? mark it unreachable)'}")
    if same_name_diff_url:
        print(f"\nPossible missed dedup (same name, different URL — resolve by hand): {same_name_diff_url}")
    print("\nGATES:")
    for g, ok in gates:
        print(f"  [{'PASS' if ok else 'FAIL'}] {g}")
    print()
    if failed:
        print(f"RESULT: {len(failed)} gate(s) FAILED — not shippable as-is.")
        return 1
    print("RESULT: all gates pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
