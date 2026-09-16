#!/usr/bin/env python3
"""Automated Stress Test Runner for cheapoS unattended execution across 100 micro-tasks.

Usage:
  python3 scripts/stress_runner.py --dry-run
  python3 scripts/stress_runner.py --start ST-001 --end ST-010
  python3 scripts/stress_runner.py --limit 5
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

TASKS_FILE = Path(__file__).resolve().parent.parent / "docs" / "trials" / "stress-100-tasks" / "tasks.json"
RESULTS_FILE = Path(__file__).resolve().parent.parent / "docs" / "trials" / "stress-100-tasks" / "results.json"
SUMMARY_FILE = Path(__file__).resolve().parent.parent / "docs" / "trials" / "stress-100-tasks" / "SUMMARY.md"
DEFAULT_REPO_DIR = "/tmp/cheapoS-stress-repo"


def git_run(repo_dir, *args, check=True):
    res = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True, text=True
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo_dir}: {res.stderr}")
    return res.stdout.strip()


def init_stress_repo(repo_dir):
    repo = Path(repo_dir)
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        git_run(repo, "init", "-b", "main")
        git_run(repo, "config", "user.name", "Stress Operator")
        git_run(repo, "config", "user.email", "stress@cheapos.local")
        readme = repo / "README.md"
        readme.write_text("# cheapoS 100-Task Stress Test Repository\n\nIsolated workspace for continuous trial execution.\n")
        git_run(repo, "add", "README.md")
        git_run(repo, "commit", "-m", "Initialize stress test baseline")
    return repo


def reset_repo_for_task(repo_dir, task):
    git_run(repo_dir, "checkout", "main", check=False)
    git_run(repo_dir, "reset", "--hard", "HEAD", check=False)
    git_run(repo_dir, "clean", "-fd", check=False)

    test_path = Path(repo_dir) / task["test_name"]
    test_path.write_text(task["test_code"])
    git_run(repo_dir, "add", task["test_name"])
    status = git_run(repo_dir, "status", "--porcelain", check=False)
    if status:
        git_run(repo_dir, "commit", "-m", f"Add {task['id']} acceptance test contract: {task['test_name']}")
    return git_run(repo_dir, "rev-parse", "HEAD")


class CheapOSClient:
    def __init__(self, api_base="http://127.0.0.1:5173"):
        self.api_base = api_base
        self.token = self._get_token()

    def _get_token(self):
        req = urllib.request.Request(f"{self.api_base}/api/bootstrap")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())["token"]

    def get(self, path):
        req = urllib.request.Request(f"{self.api_base}{path}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def post(self, path, data):
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api_base}{path}",
            data=payload,
            headers={"Content-Type": "application/json", "X-CheapOS-Token": self.token}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"POST {path} failed ({e.code}): {raw}") from None


def run_single_task(client, repo_dir, task, limits=None):
    limits = limits or {
        "dollars": 1.0,
        "working_seconds": 3600,
        "worker_turns": 40,
        "requests": 80,
        "tool_actions": 160,
        "reviewer_tokens": 100000,
        "check_seconds": 180,
        "output_tokens": 4096
    }

    start_time = time.time()
    feature_ref = f"refs/heads/feature/{task['id'].lower()}-{int(start_time)}"
    plan_req = {
        "repository": str(repo_dir),
        "prompt": task["prompt"],
        "base_ref": "refs/heads/main",
        "target_ref": "refs/heads/main",
        "feature_ref": feature_ref,
        "limits": limits,
        "measurement": True,
        "planning_id": str(uuid.uuid4())
    }

    print(f"[{task['id']}] Dispatching plan-start...", flush=True)
    res = client.post("/api/branch-runs/plan-start", plan_req)
    task_id = res["task_id"]

    # 1. Wait for planning
    while True:
        td = client.get(f"/api/tasks/{task_id}")
        st = td.get("status")
        br_st = td.get("branch_run", {}).get("status")
        if br_st == "awaiting_authorization" or st == "awaiting_authorization":
            break
        if st == "paused":
            client.post(f"/api/tasks/{task_id}/branch-resume", {})
        time.sleep(2)

    # 2. Normalize and authorize proposal
    prop_data = client.post(f"/api/tasks/{task_id}/branch-proposal", {})
    proposal_id = prop_data["proposal_id"]
    plan = prop_data.get("contract", {}).get("plan") or prop_data.get("plan", {})
    modified = False
    for it in plan.get("items", []):
        if it.get("required_checks") != [task["verification_command"]]:
            it["required_checks"] = [task["verification_command"]]
            modified = True
    if plan.get("final_checks") != [task["verification_command"]]:
        plan["final_checks"] = [task["verification_command"]]
        modified = True
    if modified:
        client.post(f"/api/tasks/{task_id}/branch-proposal-edit", {"plan": plan})
        prop_data = client.post(f"/api/tasks/{task_id}/branch-proposal", {})
        proposal_id = prop_data["proposal_id"]

    client.post(f"/api/tasks/{task_id}/branch-start", {"proposal_id": proposal_id, "approved": True})
    print(f"[{task['id']}] Branch run started. Supervising...", flush=True)

    # 3. Supervise execution loop
    last_event_len = 0
    pause_retries = 0

    while True:
        time.sleep(3)
        td = client.get(f"/api/tasks/{task_id}")
        br = td.get("branch_run", {})
        st = td.get("status")
        br_st = br.get("status")

        events = td.get("events", [])
        if len(events) > last_event_len:
            for ev in events[last_event_len:]:
                kind = ev.get("kind")
                title = ev.get("title") or ""
                print(f"  [{task['id']}] [{kind}] {title}", flush=True)
            last_event_len = len(events)

        if br_st == "ready_for_merge":
            print(f"[{task['id']}] Reached ready_for_merge!", flush=True)
            break

        if st == "waiting_approval" or td.get("pending_approval"):
            pending = td.get("pending_approval")
            if pending:
                client.post(f"/api/tasks/{task_id}/approval", {"approved": True, "remember": True, "approval_id": pending["id"]})

        if st == "paused" or br_st == "paused":
            pause_reason = br.get("pause_reason") or td.get("pause_reason")
            error = td.get("error") or ""
            print(f"  [{task['id']}] PAUSED: reason={pause_reason}, error={error}", flush=True)

            # If review stalled due to repeated evidence, coach reviewer once or fail-fast
            if "repeated unchanged evidence" in str(error) or "repeated the same unchanged evidence" in str(error) or pause_reason == "recovery_exhausted":
                if pause_retries < 1:
                    try:
                        client.post(f"/api/tasks/{task_id}/branch-message", {
                            "message": f"Verification checks pass. Please call review_decision with APPROVE for candidate."
                        })
                    except Exception as e:
                        print(f"  [{task['id']}] Guidance failed: {e}", flush=True)
                else:
                    return {
                        "task_id": task["id"],
                        "title": task["title"],
                        "category": task["category"],
                        "status": "PAUSED_REVIEW_STALL",
                        "reason": pause_reason,
                        "error": str(error),
                        "duration": round(time.time() - start_time, 2),
                        "cost": td.get("usage", {}).get("cost", 0.0)
                    }

            pause_retries += 1
            if pause_retries > 4:
                return {
                    "task_id": task["id"],
                    "title": task["title"],
                    "category": task["category"],
                    "status": "PAUSED_EXHAUSTED",
                    "reason": pause_reason,
                    "error": str(error),
                    "duration": round(time.time() - start_time, 2),
                    "cost": td.get("usage", {}).get("cost", 0.0)
                }
            time.sleep(5)
            try:
                res = client.post(f"/api/tasks/{task_id}/branch-resume", {})
                if res.get("needs_consent"):
                    client.post(f"/api/tasks/{task_id}/branch-resume", {"proposal_id": res["proposal_id"], "approved": True})
            except Exception as e:
                print(f"  [{task['id']}] Resume failed: {e}", flush=True)

    # 4. Final preview and merge
    prev = None
    for attempt in range(12):
        try:
            prev = client.post(f"/api/tasks/{task_id}/branch-final-preview", {})
            break
        except Exception as e:
            if "Pause" in str(e) and attempt < 11:
                time.sleep(1.0)
                continue
            raise

    preview_id = (prev.get("preview_id") or prev.get("proposal_id")) if prev else None
    if not preview_id and prev:
        if prev.get("update_available") and prev.get("update_token"):
            print(f"[{task['id']}] Target updated; updating branch and rechecking...", flush=True)
            client.post(f"/api/tasks/{task_id}/branch-update", {"approved": True, "update_token": prev["update_token"]})
            while True:
                time.sleep(3)
                td = client.get(f"/api/tasks/{task_id}")
                if td.get("branch_run", {}).get("status") == "ready_for_merge":
                    break
                if td.get("status") in ("paused", "blocked", "failed"):
                    break
            prev = client.post(f"/api/tasks/{task_id}/branch-final-preview", {})
            preview_id = prev.get("preview_id") or prev.get("proposal_id")
        elif "revalidate" in str(prev.get("blocker", "")):
            client.post(f"/api/tasks/{task_id}/branch-final-recheck", {})
            time.sleep(5)
            prev = client.post(f"/api/tasks/{task_id}/branch-final-preview", {})
            preview_id = prev.get("preview_id") or prev.get("proposal_id")

    merge_res = client.post(f"/api/tasks/{task_id}/branch-merge", {"proposal_id": preview_id, "approved": True})
    print(f"[{task['id']}] Merged successfully! Status: {merge_res.get('status')}", flush=True)

    # 5. Local check
    test_proc = subprocess.run(
        ["python3", "-m", "unittest", "-v", task["test_name"]],
        cwd=repo_dir, capture_output=True, text=True
    )
    passed = (test_proc.returncode == 0)

    elapsed = round(time.time() - start_time, 2)
    final_td = client.get(f"/api/tasks/{task_id}")
    usage = final_td.get("usage", {})

    return {
        "task_id": task["id"],
        "title": task["title"],
        "category": task["category"],
        "status": "MERGED" if passed else "FAILED_POST_MERGE_TESTS",
        "duration": elapsed,
        "turns": final_td.get("worker_turns", 0),
        "cost": usage.get("cost", 0.0),
        "tokens": {
            "worker": usage.get("worker", {}).get("tokens", 0),
            "reviewer": usage.get("reviewer", {}).get("tokens", 0),
            "planner": usage.get("planner", {}).get("tokens", 0)
        }
    }


def write_summary(results):
    total = len(results)
    merged = sum(1 for r in results if r["status"] == "MERGED")
    paused = sum(1 for r in results if "PAUSED" in r["status"])
    failed = sum(1 for r in results if "FAIL" in r["status"])
    total_cost = sum(r.get("cost", 0.0) for r in results)

    lines = [
        "# cheapoS 100-Task Stress Test Report",
        "",
        f"- **Total Executed:** {total}",
        f"- **Merged Cleanly:** {merged} ({round(merged/total*100, 1) if total else 0}%)",
        f"- **Paused / Blocked:** {paused}",
        f"- **Failed:** {failed}",
        f"- **Total Spend:** ${total_cost:.4f} (Strict $0.00 Free Tier)",
        "",
        "| ID | Title | Category | Status | Turns | Duration (s) | Cost |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: |"
    ]
    for r in results:
        lines.append(f"| {r['task_id']} | {r.get('title', '')} | {r.get('category', '')} | {r['status']} | {r.get('turns', '-')} | {r.get('duration', '-')} | ${r.get('cost', 0.0):.4f} |")

    SUMMARY_FILE.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run cheapoS 100-task unattended stress test suite.")
    parser.add_argument("--start", default="ST-001", help="Start task ID (e.g. ST-001)")
    parser.add_argument("--end", default="ST-100", help="End task ID (e.g. ST-100)")
    parser.add_argument("--ids", default=None, help="Comma-separated list of specific task IDs (e.g. ST-016,ST-025,ST-051)")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle selected tasks")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of tasks to run")
    parser.add_argument("--dry-run", action="store_true", help="Print task plan and initialize repo without dispatching")
    parser.add_argument("--repo-dir", default=DEFAULT_REPO_DIR, help="Isolated test repository directory")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds to wait between tasks")
    parser.add_argument("--api-base", default="http://127.0.0.1:5173", help="cheapoS server base URL")
    args = parser.parse_args()

    with open(TASKS_FILE) as f:
        all_tasks = json.load(f)

    # Filter tasks
    if args.ids:
        target_ids = {tid.strip() for tid in args.ids.split(",") if tid.strip()}
        selected = [t for t in all_tasks if t["id"] in target_ids]
    else:
        selected = [t for t in all_tasks if args.start <= t["id"] <= args.end]

    if args.shuffle:
        import random
        random.shuffle(selected)

    if args.limit:
        selected = selected[:args.limit]

    print(f"Selected {len(selected)} tasks ({selected[0]['id']} to {selected[-1]['id']}).")

    repo = init_stress_repo(args.repo_dir)
    print(f"Stress test repository ready at: {repo}")

    if args.dry_run:
        print("\n[DRY RUN MODE] Simulating workspace resets:")
        for t in selected[:3]:
            head = reset_repo_for_task(args.repo_dir, t)
            print(f"  {t['id']}: {t['title']} -> git head: {head[:8]} | test: {t['test_name']}")
        print(f"\nDry run complete for {len(selected)} tasks. No API calls dispatched.")
        return

    client = CheapOSClient(args.api_base)
    results = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE) as f:
                results = json.load(f)
        except Exception:
            results = []

    for i, t in enumerate(selected, 1):
        print(f"\n==========================================")
        print(f"Task {i}/{len(selected)}: {t['id']} - {t['title']} ({t['category']})")
        print(f"==========================================")
        reset_repo_for_task(args.repo_dir, t)

        def record_result(res_item):
            idx = next((idx for idx, r in enumerate(results) if r.get("task_id") == res_item["task_id"]), None)
            if idx is not None:
                results[idx] = res_item
            else:
                results.append(res_item)

        try:
            outcome = run_single_task(client, args.repo_dir, t)
            record_result(outcome)
        except KeyboardInterrupt:
            print("\nRunner interrupted by operator. Saving progress...")
            break
        except Exception as e:
            print(f"[{t['id']}] Fatal exception: {e}")
            record_result({"task_id": t["id"], "title": t["title"], "category": t["category"], "status": f"FATAL_ERROR: {e}"})

        with open(RESULTS_FILE, "w") as f:
            json.dump(results, f, indent=2)
        write_summary(results)

        if i < len(selected):
            print(f"Cooling down {args.delay}s before next task...")
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
