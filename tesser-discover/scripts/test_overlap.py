#!/usr/bin/env python3
"""Unit tests for overlap.py — pure-function checks, no network, no LLM.
Run: python3 test_overlap.py   (exit 0 = all pass)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAP = os.path.join(HERE, "overlap.py")

import importlib.util
spec = importlib.util.spec_from_file_location("overlap", OVERLAP)
overlap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlap)

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def run(ledger):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(ledger, f)
        path = f.name
    p = subprocess.run([sys.executable, OVERLAP, path], capture_output=True, text=True)
    os.unlink(path)
    return p.returncode, p.stdout


print("canonicalization:")
check("url scheme/www/trailing-slash/query stripped",
      overlap.canon_url("https://www.Foo.com/Bar/?x=1") == "foo.com/bar")
check("name punctuation/case folded", overlap.canon_name("Mem-0 AI!") == "mem0ai")
check("url is the identity when present",
      overlap.key({"name": "X", "url": "https://a.com"}) == "a.com")
check("name fallback when no url",
      overlap.key({"name": "Solo Tool"}) == "name:solotool")
check("same url, different names dedup to one key",
      overlap.key({"name": "A", "url": "http://z.io"}) ==
      overlap.key({"name": "B", "url": "https://z.io/"}))

# A healthy run: 8 lenses, distinct anchors, mostly new finds, a channel lens.
good = {
    "caps": {"max_searches": 18, "max_fetches": 12, "max_lenses": 10},
    "baseline": {"query": "best web search api", "finds": [{"name": "Tavily", "url": "tavily.com"}]},
    "lenses": [
        {"lens": f"L{i}", "anchor": f"anchor{i}", "channel": ("github" if i == 0 else "search"),
         "searches": 2, "fetches": 1,
         "finds": [{"name": f"Tool{i}", "url": f"t{i}.com"}]}
        for i in range(8)
    ],
}
print("\nhealthy run:")
rc, out = run(good)
check("exit 0 (all gates pass)", rc == 0)
check("reports 100% non-overlap (none in baseline)", "= 100%" in out)
check("all gates PASS, none FAIL", "FAIL" not in out)

# A bad run: too few lenses, finds all equal baseline, duplicate anchors, no channel lens.
bad = {
    "caps": {"max_searches": 18, "max_fetches": 12, "max_lenses": 10},
    "baseline": {"query": "best web search api", "finds": [{"name": "Tavily", "url": "tavily.com"}]},
    "lenses": [
        {"lens": "A", "anchor": "same", "channel": "search", "searches": 2, "fetches": 0,
         "finds": [{"name": "Tavily", "url": "tavily.com"}]},
        {"lens": "B", "anchor": "same", "channel": "search", "searches": 2, "fetches": 0,
         "finds": [{"name": "Tavily", "url": "https://www.tavily.com/"}]},
    ],
}
print("\nbad run (reproduces baseline, collapsed, dup anchors, too few lenses):")
rc, out = run(bad)
check("exit 1 (gates failed)", rc == 1)
check("non-overlap computed as 0%", "= 0%" in out)
check("collapsed lens-pair detected", "COLLAPSED" in out)
check("duplicate-anchor detected", "Duplicate anchors" in out)
check("lens_count floor FAILs", "[FAIL] lens_count >= 8" in out)
check("channel-lens gate FAILs", "[FAIL] >=1 non-search channel lens" in out)

# Budget overrun is caught.
over = dict(good)
over_lenses = [dict(l) for l in good["lenses"]]
over_lenses[0] = dict(over_lenses[0], searches=40)
over = {**good, "lenses": over_lenses}
print("\nbudget overrun:")
rc, out = run(over)
check("exit 1 on search-budget overrun", rc == 1)
check("total_searches gate FAILs", "[FAIL] total_searches <= 18" in out)

# Per-lens cap can fail even when the total is under budget.
perlens = [dict(l) for l in good["lenses"]]
perlens[0] = dict(perlens[0], searches=5)  # total = 5 + 7*2 + 1 = 20 ... keep total ok:
for k in range(1, 8):
    perlens[k] = dict(perlens[k], searches=1)  # total now 5 + 7 + 1 = 13 <= 18
perlens_led = {**good, "lenses": perlens}
print("\nper-lens cap (total under budget, one lens over):")
rc, out = run(perlens_led)
check("exit 1 (per-lens cap failed)", rc == 1)
check("total_searches gate still PASSes", "[PASS] total_searches <= 18" in out)
check("per-lens gate FAILs", "[FAIL] <= 2 searches per lens" in out)

# Empty lens allowed (reported, not fatal on its own); same-name-diff-url surfaced.
soft = {**good}
soft_lenses = [dict(l) for l in good["lenses"]]
soft_lenses[1] = dict(soft_lenses[1], finds=[])  # empty lens
soft_lenses[2] = dict(soft_lenses[2], finds=[{"name": "DupCo", "url": "dupco.com"}])
soft_lenses[3] = dict(soft_lenses[3], finds=[{"name": "DupCo", "url": "dupco.io"}])
soft = {**good, "lenses": soft_lenses}
print("\nsoft signals (empty lens + same-name/diff-url):")
rc, out = run(soft)
check("empty lens surfaced", "Empty lenses" in out)
check("same-name/diff-url surfaced", "Possible missed dedup" in out and "dupco" in out)
check("silent empty lens FAILs its gate", "[FAIL] every empty lens gives a null_reason" in out)

soft_lenses[1] = dict(soft_lenses[1], null_reason="searched two vocabularies; nothing relevant")
rc, out = run({**good, "lenses": soft_lenses})
check("empty lens with a null_reason passes", rc == 0 and "nothing relevant" in out)

# A dead source (e.g. the OpenAI helper out of credits) can't count toward the lens floor.
dead = [dict(l) for l in good["lenses"]][:7] + [
    {"lens": "Reddit", "anchor": "practitioners", "channel": "community", "searches": 0,
     "openai_calls": 1, "openai_searches": 0, "finds": [],
     "unreachable": "openai_websearch exit 4: credit_balance_exhausted"}]
print("\nunreachable lens:")
rc, out = run({**good, "lenses": dead})
check("unreachable lens reported with its reason", "credit_balance_exhausted" in out)
check("7 reached lenses fail the floor of 8", rc == 1 and "[FAIL] lens_count >= 8" in out)
check("its OpenAI call still counts toward the budget", "incl. 1 OpenAI calls" in out)

# Entrants: a lens find named in the baseline results is mainstream, even at a different URL.
ent = {**good, "baseline": {"query": "best web search api",
                            "finds": [{"name": "Top 10 search APIs", "url": "listicle.com/top10"}],
                            "entrants": [{"name": "Tool3", "url": "listicle.com/top10"}]}}
print("\nbaseline entrants:")
rc, out = run(ent)
check("find named by a baseline result counts as mainstream", "7/8 = 88%" in out)
check("mainstream entrants listed", "Mainstream entrants" in out and "Tool3" in out)
rc, out = run(good)
check("no entrants -> inflation warning", "likely inflated" in out)

# OpenAI internal searches show up in the receipt.
oa = [dict(l) for l in good["lenses"]]
oa[0] = dict(oa[0], searches=1, openai_calls=1, openai_searches=23)
rc, out = run({**good, "lenses": oa})
check("receipt shows searches run inside OpenAI calls", "ran 23 searches" in out)

# The adversarial case the Claude judge built: 8 near-synonym anchors with
# distinct literal strings + distinct finds. Must now FAIL the near-synonym gate.
syn_anchors = ["search ranking bias", "search ranking skew", "search ranking coverage",
               "search ranking depth", "search ranking freshness", "search ranking region",
               "search ranking authority", "search ranking namesake"]
adversarial = {
    "caps": {"max_searches": 18, "max_fetches": 12, "max_lenses": 10},
    "baseline": {"query": "best web search api", "finds": [{"name": "Tavily", "url": "tavily.com"}]},
    "lenses": [
        {"lens": f"L{i}", "anchor": syn_anchors[i], "channel": ("github" if i == 0 else "search"),
         "searches": 1, "fetches": 0, "finds": [{"name": f"New{i}", "url": f"n{i}.com"}]}
        for i in range(8)
    ],
}
print("\nadversarial near-synonym lenses (distinct strings, distinct finds):")
rc, out = run(adversarial)
check("exit 1 (near-synonym gate caught it)", rc == 1)
check("near-synonym gate FAILs", "[FAIL] no near-synonym anchor pairs" in out)
check("shared tokens reported (search/ranking)", "ranking" in out and "search" in out)
check("healthy run does NOT false-trip near-synonym", True)  # asserted below
rc2, out2 = run(good)
check("healthy run still passes (no false near-synonym)", rc2 == 0 and "no near-synonym anchor pairs" in out2 and "[FAIL]" not in out2)

print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("ALL TESTS PASSED")
