#!/usr/bin/env python3
"""openai_websearch.py — search the web through OpenAI's Responses API `web_search` tool.

The reason it exists: Claude's WebSearch refuses reddit.com (HTTP 400, crawler
blocked) and Reddit's own JSON API refuses scripted requests, so this is the one
programmatic path to Reddit threads and other community posts. It also reads some
Cloudflare-walled pages WebFetch can't.

Usage:
    openai_websearch.py "<query or instruction>" [--json] [--max-output-tokens N] [--model M]

Prints the answer text, then one `SOURCE: <url>` line per cited URL. A receipt goes
to stderr: response status, how many web searches OpenAI ran inside the call, and
tokens. With --json, prints {"text", "sources", "searches", "status", "usage"} instead.

One call can run many searches internally (a 2-call run once ran 47), so log the
receipt's `searches` count in the discover ledger, not just "1 call".

These calls are billed to the OpenAI API credits, not a subscription. Every completed
call appends its usage (tokens by kind, searches, response id, the Claude session
that ran it) to ~/.local/state/openai-usage/calls.jsonl (override: OPENAI_USAGE_LOG);
the token-cost skill prices that log (`token_cost.py openai`).

A call routinely takes 1-5 minutes: run it with the Bash tool's run_in_background,
or a timeout of at least 600000 ms.

Exit codes: 0 ok · 2 usage · 3 OPENAI_API_KEY not set · 4 API error (the message
names OpenAI's error code, e.g. credit_balance_exhausted) · 5 network error.
Defaults (gpt-5, low reasoning effort, large output budget) follow what earlier runs
found: high effort plus many searches used up the output budget before any text.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.openai.com/v1/responses"


def parse(resp):
    """Pull text, cited URLs and the internal search count out of a Responses API body."""
    texts, sources, searches = [], [], 0
    for item in resp.get("output", []):
        if item.get("type") == "web_search_call":
            searches += 1
        elif item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") != "output_text":
                    continue
                texts.append(part.get("text", ""))
                for ann in part.get("annotations", []):
                    url = ann.get("url")
                    if ann.get("type") == "url_citation" and url and url not in sources:
                        sources.append(url)
    return {"text": "\n".join(texts), "sources": sources, "searches": searches,
            "status": resp.get("status"), "usage": resp.get("usage", {})}


def usage_fields(usage):
    return {"input_tokens": usage.get("input_tokens", 0),
            "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)}


def log_call(resp, out, a):
    """Append one line per billed call, so the token-cost skill can price what the API credits paid for."""
    path = os.environ.get("OPENAI_USAGE_LOG",
                          os.path.expanduser("~/.local/state/openai-usage/calls.jsonl"))
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "tool": "openai_websearch", "response_id": resp.get("id"), "model": resp.get("model") or a.model,
           "status": out["status"], "web_search_calls": out["searches"], **usage_fields(out["usage"]),
           "claude_session": os.environ.get("CLAUDE_CODE_SESSION_ID"), "cwd": os.getcwd(),
           "query": a.query[:200]}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError as e:
        print(f"openai_websearch: couldn't write usage log {path}: {e}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("query")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-output-tokens", type=int, default=16000)
    ap.add_argument("--model", default=os.environ.get("OPENAI_WEBSEARCH_MODEL", "gpt-5"))
    a = ap.parse_args(argv)

    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("openai_websearch: OPENAI_API_KEY is not set; this lens can't run.", file=sys.stderr)
        return 3

    body = {"model": a.model, "reasoning": {"effort": "low"},
            "max_output_tokens": a.max_output_tokens,
            "tools": [{"type": "web_search", "search_context_size": "high"}],
            "input": a.query}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            err = json.loads(detail).get("error", {})
            detail = f"{err.get('code') or err.get('type')}: {err.get('message')}"
        except ValueError:
            detail = detail[:300]
        print(f"openai_websearch: HTTP {e.code} — {detail}", file=sys.stderr)
        return 4
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"openai_websearch: network error — {e}", file=sys.stderr)
        return 5

    out = parse(resp)
    log_call(resp, out, a)
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(out["text"])
        for url in out["sources"]:
            print(f"SOURCE: {url}")
    u = usage_fields(out["usage"])
    print(f"[status: {out['status']}  searches: {out['searches']}  input: {u['input_tokens']} "
          f"(cached {u['cached_tokens']})  output: {u['output_tokens']}  "
          f"(cost: token-cost skill, `token_cost.py openai`)]", file=sys.stderr)
    if out["status"] != "completed":
        print("openai_websearch: response did not complete; raise --max-output-tokens or narrow the query.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
