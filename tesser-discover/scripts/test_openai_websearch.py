#!/usr/bin/env python3
"""Unit tests for openai_websearch.py — no network. Run: python3 test_openai_websearch.py"""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "openai_websearch.py")
spec = importlib.util.spec_from_file_location("ows", PATH)
ows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ows)

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


resp = {"status": "completed", "usage": {"total_tokens": 1200}, "output": [
    {"type": "reasoning"},
    {"type": "web_search_call", "status": "completed"},
    {"type": "web_search_call", "status": "completed"},
    {"type": "message", "content": [{"type": "output_text", "text": "Answer.", "annotations": [
        {"type": "url_citation", "url": "https://www.reddit.com/r/ynab/comments/1"},
        {"type": "url_citation", "url": "https://www.reddit.com/r/ynab/comments/1"},
        {"type": "url_citation", "url": "https://example.com/post"}]}]}]}
out = ows.parse(resp)
print("parse:")
check("counts internal web searches", out["searches"] == 2)
check("dedups cited URLs, keeps order", out["sources"] == [
    "https://www.reddit.com/r/ynab/comments/1", "https://example.com/post"])
check("keeps answer text", out["text"] == "Answer.")
check("passes status through", out["status"] == "completed")

print("usage log:")
import json, tempfile, types
with tempfile.TemporaryDirectory() as d:
    os.environ["OPENAI_USAGE_LOG"] = os.path.join(d, "calls.jsonl")
    os.environ["CLAUDE_CODE_SESSION_ID"] = "sess-123"
    full = dict(resp, id="resp_1", model="gpt-5-2025-08-07",
                usage={"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 200},
                       "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 100}})
    ows.log_call(full, ows.parse(full), types.SimpleNamespace(model="gpt-5", query="q" * 300))
    rec = json.loads(open(os.environ["OPENAI_USAGE_LOG"]).read().splitlines()[0])
check("logs tokens by kind", (rec["input_tokens"], rec["cached_tokens"], rec["output_tokens"],
                              rec["reasoning_tokens"]) == (1000, 200, 300, 100))
check("logs searches, response id, model and Claude session",
      (rec["web_search_calls"], rec["response_id"], rec["model"], rec["claude_session"]) ==
      (2, "resp_1", "gpt-5-2025-08-07", "sess-123"))
check("truncates the logged query", len(rec["query"]) == 200)

print("missing key:")
env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
p = subprocess.run([sys.executable, PATH, "q"], capture_output=True, text=True, env=env)
check("exits 3 without OPENAI_API_KEY", p.returncode == 3)
check("says the lens can't run", "can't run" in p.stderr)

print()
if failures:
    print(f"{len(failures)} FAILED")
    sys.exit(1)
print("ALL TESTS PASSED")
