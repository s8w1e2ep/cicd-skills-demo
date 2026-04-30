#!/usr/bin/env python3
"""Trigger-precision eval harness for the CI/CD Skills.

Sends every prompt in `eval/prompts.jsonl` to the live `/run` endpoint and
scores the response against `expected_skill`. Three categories:

  single      expected = "<skill-name>"           — exactly one Skill must fire
  compound    expected = "ANY:skill1,skill2,..."  — any one of the listed Skills is acceptable
  misleading  expected = "REFUSE"                 — must return status="refused"

Each prompts.jsonl entry also carries a `purpose` field (free-form string)
describing what the test case is verifying. The misses section of the
markdown report includes that purpose so a reader can see why each failing
case was added.

Writes a markdown report under `eval/results/<timestamp>.md` and prints a
per-category precision summary. Reads no secrets — calls the running service
which already has the GitHub PAT and auth credential set.

Usage:
  python eval/run_eval.py [URL] [PROMPTS_FILE]
  EVAL_URL=https://x.zeabur.app python eval/run_eval.py
  python eval/run_eval.py https://x.zeabur.app --limit 5    # quick smoke

Side effects: every passing trigger prompt may write a workflow file on the
demo branch on first run. Subsequent runs return no_change for the same input,
so re-running the eval is cheap and does not spam the branch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_PROMPTS = Path(__file__).parent / "prompts.jsonl"
DEFAULT_RESULTS = Path(__file__).parent / "results"
DEFAULT_TIMEOUT_S = 240  # one /run can take 30-90s for real Skill execution


def call_run(url: str, prompt: str, timeout: int) -> dict:
    """POST /run synchronously. Returns the parsed body or {"_error": "..."}."""
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/run",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_error": f"HTTP {e.code}: {body[:200]}"}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"_error": f"Network error: {e}"}
    except json.JSONDecodeError as e:
        return {"_error": f"Bad JSON response: {e}"}


def evaluate_one(entry: dict, response: dict) -> dict:
    """Apply the per-category match rule and return a flat result row.

    REFUSE prompts pass when status="refused" — this covers both Skills
    that internally refuse (rare) and the wrapper-driven no-Skill-matched
    case that emits {"skill": null, "status": "refused", "message": ...}
    via NO_SKILL_FALLBACK_INSTRUCTION in server/main.py.
    """
    expected = entry["expected_skill"]
    category = entry["category"]

    if "_error" in response:
        actual_skill = None
        actual_status = f"ERROR: {response['_error']}"
        passed = False
    else:
        out = response.get("output") or {}
        actual_skill = out.get("skill")
        actual_status = out.get("status")
        if expected == "REFUSE":
            passed = actual_status == "refused"
        elif expected.startswith("ANY:"):
            acceptable = {s.strip() for s in expected[len("ANY:") :].split(",")}
            passed = actual_skill in acceptable
        else:
            passed = actual_skill == expected

    return {
        "category": category,
        "prompt": entry["prompt"],
        "purpose": entry.get("purpose", ""),
        "expected": expected,
        "actual_skill": actual_skill,
        "actual_status": actual_status,
        "duration_s": response.get("duration_s") if "_error" not in response else None,
        "passed": passed,
    }


def write_report(results: list[dict], url: str, out_dir: Path) -> Path:
    """Render the markdown report. Returns the file path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = out_dir / f"eval-{ts}.md"

    by_cat: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_cat.setdefault(r["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        if r["passed"]:
            bucket["passed"] += 1

    overall_passed = sum(b["passed"] for b in by_cat.values())
    overall_total = sum(b["total"] for b in by_cat.values())
    overall_prec = overall_passed / overall_total if overall_total else 0.0

    with out_file.open("w") as f:
        f.write(f"# Eval results — {ts}\n\n")
        f.write(f"Endpoint: `{url}`\n\n")
        f.write(f"Overall: **{overall_passed}/{overall_total} = {overall_prec:.0%}**\n\n")
        f.write("## Per-category precision\n\n")
        f.write("| Category | Pass | Total | Precision |\n")
        f.write("|---|---:|---:|---:|\n")
        for cat in ("single", "compound", "misleading"):
            b = by_cat.get(cat, {"passed": 0, "total": 0})
            prec = (b["passed"] / b["total"]) if b["total"] else 0.0
            f.write(f"| {cat} | {b['passed']} | {b['total']} | {prec:.0%} |\n")
        f.write("\n## Per-prompt results\n\n")
        f.write("| # | Cat | Prompt | Expected | Actual skill | Status | Pass |\n")
        f.write("|---|---|---|---|---|---|:---:|\n")
        for i, r in enumerate(results, 1):
            mark = "✅" if r["passed"] else "❌"
            short = r["prompt"][:80].replace("|", "\\|").replace("\n", " ")
            f.write(
                f"| {i} | {r['category']} | {short} | "
                f"`{r['expected']}` | `{r['actual_skill']}` | "
                f"`{r['actual_status']}` | {mark} |\n"
            )
        # Misses block — useful when revising descriptions or eval prompts.
        # Includes each entry's `purpose` so the reader can see what the test
        # was checking without going back to prompts.jsonl.
        misses = [r for r in results if not r["passed"]]
        if misses:
            f.write("\n## Misses\n\n")
            for r in misses:
                f.write(f"- **[{r['category']}]** prompt: {r['prompt']!r}\n")
                if r.get("purpose"):
                    f.write(f"  - purpose: {r['purpose']}\n")
                f.write(f"  - expected `{r['expected']}`, got skill=`{r['actual_skill']}` status=`{r['actual_status']}`\n")

    return out_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the trigger-precision eval.")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("EVAL_URL", "http://localhost:8000"),
        help="Base URL of the running service (env: EVAL_URL).",
    )
    parser.add_argument(
        "prompts",
        nargs="?",
        default=str(DEFAULT_PROMPTS),
        help=f"Path to prompts.jsonl (default: {DEFAULT_PROMPTS.relative_to(Path.cwd()) if DEFAULT_PROMPTS.is_relative_to(Path.cwd()) else DEFAULT_PROMPTS}).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N prompts.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-request timeout (s).")
    args = parser.parse_args()

    entries = []
    with open(args.prompts) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    if args.limit:
        entries = entries[: args.limit]

    print(f"Running {len(entries)} prompts against {args.url} (timeout {args.timeout}s each)...\n")

    results = []
    for i, entry in enumerate(entries, 1):
        cat = entry["category"]
        short = entry["prompt"][:60].replace("\n", " ")
        print(f"[{i}/{len(entries)}] {cat}: {short!r}", flush=True)
        t0 = time.monotonic()
        response = call_run(args.url, entry["prompt"], args.timeout)
        elapsed = time.monotonic() - t0
        result = evaluate_one(entry, response)
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(
            f"    -> {mark} expected={result['expected']} "
            f"actual_skill={result['actual_skill']} status={result['actual_status']} "
            f"({elapsed:.1f}s)\n",
            flush=True,
        )

    report = write_report(results, args.url, DEFAULT_RESULTS)
    print(f"\nReport: {report}")

    # Console summary
    by_cat: dict[str, dict[str, int]] = {}
    for r in results:
        b = by_cat.setdefault(r["category"], {"passed": 0, "total": 0})
        b["total"] += 1
        if r["passed"]:
            b["passed"] += 1
    print("\nSummary:")
    for cat in ("single", "compound", "misleading"):
        b = by_cat.get(cat, {"passed": 0, "total": 0})
        prec = (b["passed"] / b["total"]) if b["total"] else 0.0
        print(f"  {cat:10s}  {b['passed']}/{b['total']}  {prec:.0%}")

    # Exit non-zero if single-trigger precision is below the 0.85 target — useful in CI.
    # We gate on the `single` category because that's the most direct measure of
    # description-level routing precision; compound and misleading test broader
    # behaviours where a partial miss isn't necessarily a description problem.
    single_b = by_cat.get("single", {"passed": 0, "total": 0})
    single_prec = (single_b["passed"] / single_b["total"]) if single_b["total"] else 0.0
    return 0 if single_prec >= 0.85 else 1


if __name__ == "__main__":
    sys.exit(main())
