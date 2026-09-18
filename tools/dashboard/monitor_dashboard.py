#!/usr/bin/env python3
"""Read-only RoboDojo monitor and local HTTP dashboard.

This utility only reads the campaign output tree.  It never launches, stops,
or edits an evaluation; ``state.json`` is the only file it writes, and that
file lives beside this dashboard rather than in the experiment output.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

DEFAULT_ROOT = Path(os.environ.get("STARROBOHARNESS_RUN_ROOT", "."))
DEFAULT_ASSET_DIR = Path(
    os.environ.get("STARROBOHARNESS_DASHBOARD_DIR", Path(__file__).resolve().parent)
)
CAMERAS = ("cam_high", "cam_left_wrist", "cam_right_wrist")
HISTORY_ROOTS = ()
ASTRA_RATES = {"input": 10.0, "cached_input": 1.0, "output": 50.0}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, OSError, ValueError):
        return default


def tail(path: Path, lines: int = 12):
    try:
        return path.read_text(errors="replace").splitlines()[-lines:]
    except (FileNotFoundError, OSError):
        return []


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _usage_value(usage, camel, snake):
    value = usage.get(camel, usage.get(snake, 0))
    return value if isinstance(value, (int, float)) else 0


def _empty_usage():
    return {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_files": 0,
    }


def aggregate_usage(root: Path):
    total = _empty_usage()
    for usage_path in root.rglob("reasoner/usage.json"):
        usage = read_json(usage_path, {}) or {}
        total["input_tokens"] += _usage_value(usage, "inputTokens", "input_tokens")
        total["cached_input_tokens"] += _usage_value(
            usage, "cachedInputTokens", "cached_input_tokens"
        )
        total["output_tokens"] += _usage_value(usage, "outputTokens", "output_tokens")
        total["usage_files"] += 1
    total["total_tokens"] = total["input_tokens"] + total["output_tokens"]
    total["uncached_input_tokens"] = max(
        0, total["input_tokens"] - total["cached_input_tokens"]
    )
    total["standard_estimate_usd"] = (
        total["uncached_input_tokens"] / 1_000_000 * ASTRA_RATES["input"]
        + total["cached_input_tokens"] / 1_000_000 * ASTRA_RATES["cached_input"]
        + total["output_tokens"] / 1_000_000 * ASTRA_RATES["output"]
    )
    total["all_long_context_estimate_usd"] = (
        total["uncached_input_tokens"] / 1_000_000 * ASTRA_RATES["input"] * 2
        + total["cached_input_tokens"] / 1_000_000 * ASTRA_RATES["cached_input"] * 2
        + total["output_tokens"] / 1_000_000 * ASTRA_RATES["output"] * 1.5
    )
    return total


def reasoner_turns(root: Path):
    turns = 0
    for result_path in root.rglob("smoke-result.json"):
        result = read_json(result_path, {}) or {}
        turns += (result.get("metrics") or {}).get("reasoner_calls", 0) or 0
    for outcome_path in root.glob("*/*/outcome.json"):
        outcome = read_json(outcome_path, {}) or {}
        turns += (outcome.get("metrics") or {}).get("reasoner_calls", 0) or 0
    return turns


def cost_summary(root: Path, history_roots):
    current = aggregate_usage(root)
    current["reasoner_turns"] = reasoner_turns(root)
    retained = _empty_usage()
    retained["reasoner_turns"] = 0
    roots = []
    for history_root in history_roots:
        if history_root.resolve() == root.resolve() or not history_root.exists():
            continue
        usage = aggregate_usage(history_root)
        for key in retained:
            if key in usage:
                retained[key] += usage[key]
        retained["reasoner_turns"] += reasoner_turns(history_root)
        roots.append(str(history_root))
    retained["uncached_input_tokens"] = max(
        0, retained["input_tokens"] - retained["cached_input_tokens"]
    )
    retained["standard_estimate_usd"] = (
        retained["uncached_input_tokens"] / 1_000_000 * ASTRA_RATES["input"]
        + retained["cached_input_tokens"] / 1_000_000 * ASTRA_RATES["cached_input"]
        + retained["output_tokens"] / 1_000_000 * ASTRA_RATES["output"]
    )
    retained["all_long_context_estimate_usd"] = (
        retained["uncached_input_tokens"] / 1_000_000 * ASTRA_RATES["input"] * 2
        + retained["cached_input_tokens"] / 1_000_000 * ASTRA_RATES["cached_input"] * 2
        + retained["output_tokens"] / 1_000_000 * ASTRA_RATES["output"] * 1.5
    )
    combined = aggregate_usage(root)
    combined["reasoner_turns"] = current["reasoner_turns"] + retained["reasoner_turns"]
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "usage_files",
    ):
        combined[key] = current[key] + retained[key]
    combined["uncached_input_tokens"] = max(
        0, combined["input_tokens"] - combined["cached_input_tokens"]
    )
    combined["standard_estimate_usd"] = current["standard_estimate_usd"] + retained[
        "standard_estimate_usd"
    ]
    combined["all_long_context_estimate_usd"] = (
        current["all_long_context_estimate_usd"] + retained["all_long_context_estimate_usd"]
    )
    return {
        "pricing": {
            "model": "gpt-6-astra",
            "input_usd_per_million": ASTRA_RATES["input"],
            "cached_input_usd_per_million": ASTRA_RATES["cached_input"],
            "output_usd_per_million": ASTRA_RATES["output"],
            "source": "OpenAI official GPT-6 Astra model pricing",
            "note": "Usage files are asynchronous snapshots, not final account billing.",
        },
        "current_campaign": current,
        "retained_development": retained,
        "combined": combined,
        "retained_roots": roots,
    }


def method_stats(root: Path, panel: dict, outcomes: list, method: str):
    planned = sum(1 for case in panel.get("cases", []) if method in panel.get("methods", []))
    method_rows = [row for row in outcomes if row.get("method") == method]
    valid_rows = [row for row in method_rows if row.get("valid_for_success_rate") is True]
    success_rows = [row for row in valid_rows if row.get("success") is True]
    scores = [row.get("score") for row in valid_rows if isinstance(row.get("score"), (int, float))]
    errors = []
    for error_path in sorted((root / method).glob("*/error.json")):
        error = read_json(error_path, {}) or {}
        errors.append(
            {
                "case": error_path.parent.name,
                "type": error.get("type", "unknown"),
                "message": (error.get("traceback", "").splitlines()[-1:] or [""])[0],
            }
        )
    return {
        "valid": len(valid_rows),
        "planned": planned,
        "successes": len(success_rows),
        "score": (sum(scores) / len(scores) * 100 if scores else None),
        "coverage": len(valid_rows) / planned if planned else 0,
        "errors": errors,
        "error_count": len(errors),
    }


def _result_cells(rows: list, planned: int):
    valid = [row for row in rows if row.get("valid_for_success_rate") is True]
    successes = sum(row.get("success") is True for row in valid)
    scores = [row.get("score") for row in valid if isinstance(row.get("score"), (int, float))]
    return {
        "valid": len(valid),
        "planned": planned,
        "successes": successes,
        "success_rate": successes / len(valid) if valid else None,
        "score": sum(scores) / len(scores) * 100 if scores else None,
    }


def result_table(panel: dict, outcomes: list):
    methods = panel.get("methods", [])
    task_names = list(dict.fromkeys(case.get("task") for case in panel.get("cases", [])))
    rows = []
    for task in task_names:
        case_ids = {
            case.get("case_id") for case in panel.get("cases", []) if case.get("task") == task
        }
        row = {"task": task, "planned_cases": len(case_ids), "methods": {}}
        for method in methods:
            selected = [
                outcome
                for outcome in outcomes
                if outcome.get("method") == method and outcome.get("case_id") in case_ids
            ]
            row["methods"][method] = _result_cells(selected, len(case_ids))
        rows.append(row)
    overall = {"task": "overall", "planned_cases": len(panel.get("cases", [])), "methods": {}}
    for method in methods:
        selected = [outcome for outcome in outcomes if outcome.get("method") == method]
        overall["methods"][method] = _result_cells(selected, len(panel.get("cases", [])))
    return {"methods": methods, "rows": rows, "overall": overall}


def gpt_decision_timeline(root: Path, limit=None):
    # Simulator receipts live on the AWS pod's local FSx view.  The controller
    # mirrors every decision into its local supervisor log, which is the
    # authoritative read-only source available to this CVM dashboard.
    log_path = root.parent / f"{root.name}-supervisor" / "campaign.log"
    timeline = []
    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except (FileNotFoundError, OSError):
        lines = []
    for line in reversed(lines):
        try:
            decision = json.loads(line)
        except ValueError:
            continue
        if decision.get("schema") != "robodojo_rollout.codex_decision.v1":
            continue
        response = decision.get("response") or {}
        assessment = response.get("assessment") or {}
        progress = assessment.get("task_progress") or {}
        record_path = (decision.get("simulator_receipt") or {}).get("record_path", "")
        parts = Path(record_path).parts
        try:
            case = parts[parts.index("qwenpi_v3_plus_gpt") + 1]
        except (ValueError, IndexError):
            case = decision.get("episode_id", "unknown episode")
        timeline.append(
            {
                "recorded_at": decision.get("recorded_at"),
                "case": case,
                "step_id": decision.get("step_id"),
                "decision": decision.get("decision"),
                "mode": decision.get("mode"),
                "override": bool(decision.get("codex_override")),
                "requested_steps": decision.get("requested_steps"),
                "reason": decision.get("reason"),
                "subgoal": assessment.get("current_subgoal"),
                "execution_status": assessment.get("execution_status"),
                "execution_evidence": assessment.get("execution_evidence"),
                "intent_status": assessment.get("intent_status"),
                "intent_evidence": assessment.get("intent_evidence"),
                "expected_next_intent": assessment.get("expected_next_intent"),
                "predicted_next_intent": assessment.get("predicted_next_intent"),
                "verified_completed": progress.get("verified_completed", []),
                "remaining": progress.get("remaining", []),
            }
        )
        if limit is not None and len(timeline) >= limit:
            break
    return timeline


def active_runs(root: Path, outcomes: list, freshness_seconds: int = 600):
    terminal = {
        (row.get("method"), row.get("case_id"))
        for row in outcomes
        if row.get("complete") or row.get("valid_for_success_rate")
    }
    now = time.time()
    active = []
    for path in root.glob("*/*/controller/progress.json"):
        method, case = path.parents[2].name, path.parents[1].name
        if (method, case) in terminal or now - path.stat().st_mtime > freshness_seconds:
            continue
        progress = read_json(path, {}) or {}
        active.append(
            {
                "method": method,
                "case": case,
                "step_id": progress.get("step_id"),
                "decisions": progress.get("decisions"),
                "updated_seconds_ago": round(now - path.stat().st_mtime),
            }
        )
    # GPT-direct episodes do not have a policy controller.  Their durable
    # app-server stream and tool ledger are the equivalent live receipt.
    seen = {(item["method"], item["case"]) for item in active}
    for path in root.glob("*/*/reasoner/rpc_out.jsonl"):
        method, case = path.parents[2].name, path.parents[1].name
        if (method, case) in terminal or (method, case) in seen:
            continue
        if now - path.stat().st_mtime > freshness_seconds:
            continue
        requests = list(path.parent.glob("tool_*_request.json"))
        action_count = 0
        for request_path in requests:
            request = read_json(request_path, {}) or {}
            if request.get("tool") in {"robodojo_act", "robodojo_execute"}:
                action_count += 1
        active.append(
            {
                "method": method,
                "case": case,
                "step_id": action_count,
                "decisions": len(requests),
                "reasoner_calls": 1,
                "updated_seconds_ago": round(now - path.stat().st_mtime),
            }
        )
    return sorted(active, key=lambda item: item["case"])


def latest_progress(root: Path, case_ids=None):
    candidates = list(root.glob("*/*/controller/progress.json"))
    if case_ids is not None:
        candidates = [path for path in candidates if path.parents[1].name in case_ids]
    if not candidates:
        return {}
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    progress = read_json(path, {}) or {}
    method = path.parent.parent.parent.name
    case = path.parent.parent.name
    progress.update({"method": method, "case": case})
    return progress


def media_info(root: Path, case_ids=None, media_prefix="/media"):
    """Return the newest playable recording or live RGB camera frame set.

    RoboDojo's controller writes per-step RGB PNGs rather than an MP4 while an
    episode is running.  The dashboard therefore presents the newest camera
    frame set as a live stream and switches to a recorded video if one exists.
    """
    videos = []
    for suffix in ("*.mp4", "*.webm", "*.mov", "*.mkv"):
        videos.extend(root.rglob(suffix))
    if case_ids is not None:
        videos = [
            path
            for path in videos
            if len(path.parts) > len(root.parts) + 1
            and path.parts[len(root.parts) + 1] in case_ids
        ]
    if videos:
        video = max(videos, key=lambda path: path.stat().st_mtime)
        return {
            "mode": "video",
            "url": media_prefix + "/" + quote(video.relative_to(root).as_posix(), safe="/"),
            "method": video.parts[len(root.parts)],
            "case": video.parts[len(root.parts) + 1],
            "step": None,
        }
    high_frames = list(root.glob("*/*/controller/observations/*/cam_high.png"))
    if case_ids is not None:
        high_frames = [path for path in high_frames if path.parents[3].name in case_ids]
    if not high_frames:
        return {"mode": "none", "message": "等待仿真相机帧；当前 episode 尚未进入控制阶段。"}
    high = max(high_frames, key=lambda path: path.stat().st_mtime)
    frame_dir = high.parent
    method = high.parents[4].name
    case = high.parents[3].name
    observation_root = root / method / case / "controller" / "observations"
    frame_steps = sorted(
        (path.parent.name for path in observation_root.glob("*/cam_high.png")),
        key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
    )
    camera_urls = {}
    for camera in CAMERAS:
        camera_path = frame_dir / f"{camera}.png"
        if camera_path.exists():
            relative_path = quote(camera_path.relative_to(root).as_posix(), safe="/")
            camera_urls[camera] = f"{media_prefix}/{relative_path}"
    return {
        "mode": "frames",
        "method": method,
        "case": case,
        "step": frame_dir.name,
        "cameras": camera_urls,
        "frame_steps": frame_steps,
        "frame_base": f"{media_prefix}/"
        + quote(observation_root.relative_to(root).as_posix(), safe="/"),
        "camera_names": list(CAMERAS),
    }


def evidence_roots(root: Path, outcomes: list):
    roots = [root.resolve()]
    for row in outcomes:
        source = row.get("source_run")
        if not source:
            continue
        candidate = Path(source).resolve()
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def latest_progress_across(roots, case_ids=None):
    candidates = []
    for root in roots:
        candidates.extend(root.glob("*/*/controller/progress.json"))
    if case_ids is not None:
        candidates = [path for path in candidates if path.parents[1].name in case_ids]
    if not candidates:
        return {}
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    progress = read_json(path, {}) or {}
    progress.update(
        {
            "method": path.parent.parent.parent.name,
            "case": path.parent.parent.name,
            "source_run": str(path.parents[3]),
        }
    )
    return progress


def timeline_across(roots):
    records = []
    seen = set()
    for root in roots:
        for item in gpt_decision_timeline(root):
            key = (item.get("case"), item.get("step_id"), item.get("recorded_at"))
            if key in seen:
                continue
            seen.add(key)
            records.append(item)
    return sorted(records, key=lambda item: item.get("recorded_at") or "", reverse=True)


def media_info_across(roots, case_ids, preferred_case=None):
    selected = {preferred_case} if preferred_case else case_ids
    candidates = []
    for index, root in enumerate(roots):
        paths = []
        for suffix in ("*.mp4", "*.webm", "*.mov", "*.mkv"):
            paths.extend(root.rglob(suffix))
        paths.extend(root.glob("*/*/controller/observations/*/cam_high.png"))
        paths = [
            path
            for path in paths
            if len(path.parts) > len(root.parts) + 1
            and path.parts[len(root.parts) + 1] in selected
        ]
        if paths:
            candidates.append((max(path.stat().st_mtime for path in paths), index, root))
    if not candidates and preferred_case:
        return media_info_across(roots, case_ids)
    if not candidates:
        return {"mode": "none", "message": "等待仿真相机帧；当前 episode 尚未进入控制阶段。"}
    _, index, selected_root = max(candidates)
    return media_info(selected_root, selected, media_prefix=f"/media/{index}")


def task_views(root: Path, panel: dict, outcomes: list, errors: list, timeline: list, roots=None):
    """Build stable, task-scoped views so the browser never chases global latest state."""
    roots = roots or [root]
    rows_by_task = {row["task"]: row for row in result_table(panel, outcomes)["rows"]}
    active = active_runs(root, outcomes)
    campaign_log = tail(root.parent / f"{root.name}-supervisor" / "campaign.log", lines=1200)
    views = {}
    for task in dict.fromkeys(case.get("task") for case in panel.get("cases", [])):
        cases = [case for case in panel.get("cases", []) if case.get("task") == task]
        case_ids = {case.get("case_id") for case in cases}
        latest = latest_progress_across(roots, case_ids)
        scoped_errors = [error for error in errors if error.get("case") in case_ids]
        scoped_timeline = [item for item in timeline if item.get("case") in case_ids][:30]
        current = next((case for case in cases if case.get("case_id") == latest.get("case")), {})
        if not current and scoped_errors:
            current = next(
                (case for case in cases if case.get("case_id") == scoped_errors[-1].get("case")),
                {},
            )
        views[task] = {
            "task": task,
            "case": current,
            "cases": cases,
            "latest": latest,
            "active_runs": [item for item in active if item.get("case") in case_ids],
            "errors": scoped_errors,
            "timeline": scoped_timeline,
            "video": media_info_across(
                roots,
                case_ids,
                preferred_case=scoped_timeline[0].get("case") if scoped_timeline else None,
            ),
            "results": rows_by_task.get(task, {}),
            "log_tail": [
                line for line in campaign_log if any(case_id in line for case_id in case_ids)
            ][-12:],
        }
    return views


def collect(root: Path, history_roots=HISTORY_ROOTS):
    panel = read_json(root / "panel.json", {}) or {}
    outcomes = read_json(root / "outcomes.json", []) or []
    comparison = read_json(root / "comparison.json", {}) or {}
    campaign = read_json(root / "campaign-status.json", {}) or {}
    config = read_json(root / "config.json", {}) or {}
    errors = []
    for error_path in sorted(root.glob("*/*/error.json")):
        error = read_json(error_path, {}) or {}
        entered_control = any(
            (error_path.parent / "controller" / name).exists()
            for name in ("run.json", "progress.json", "history.json")
        )
        message = (error.get("traceback", "").splitlines()[-1:] or [""])[0]
        errors.append(
            {
                "method": error_path.parent.parent.name,
                "case": error_path.parent.name,
                "type": error.get("type", "unknown"),
                "message": message,
                "entered_control": entered_control,
                "recovery": (
                    "safe_pre_control_retry"
                    if not entered_control and "port-forward" in message
                    else "manual_receipt_review"
                ),
            }
        )
    planned = len(panel.get("cases", [])) * len(panel.get("methods", []))
    valid = sum(row.get("valid_for_success_rate") is True for row in outcomes)
    invalid_attempts = [row for row in outcomes if row.get("valid_for_success_rate") is False]
    state = "WAITING TO START" if not panel else "RUNNING"
    run_note = "评测正在继续；pending 不计作失败。"
    if invalid_attempts and panel and not campaign.get("finished"):
        state = "DRAINING / INCOMPLETE"
        run_note = (
            "已出现基础设施中断；冻结调度器会让当前在途 episode 收尾后停止，"
            "不会自动完成剩余计划。"
        )
    if campaign.get("finished"):
        state = "COMPLETE" if campaign.get("complete") else "STOPPED / INCOMPLETE"
        run_note = "全部计划已完成。" if campaign.get("complete") else "本批次未完成全部计划。"
    roots = evidence_roots(root, outcomes)
    latest = latest_progress_across(roots)
    video = media_info_across(roots, {case.get("case_id") for case in panel.get("cases", [])})
    latest_error = errors[-1] if errors else None
    task_by_case = {case.get("case_id"): case for case in panel.get("cases", [])}
    current_case = task_by_case.get(latest.get("case"), {})
    if not current_case and latest_error:
        current_case = task_by_case.get(latest_error["case"], {})
    log_lines = tail(root.parent.joinpath(root.name + "-supervisor", "campaign.log"))
    timeline = timeline_across(roots)
    views = task_views(root, panel, outcomes, errors, timeline, roots)
    return {
        "generated_at": utc_now(),
        "root": str(root),
        "evidence_roots": [str(path) for path in roots],
        "status": {
            "state": state,
            "finished": bool(campaign.get("finished")),
            "valid": valid,
            "planned": planned,
            "paired": len(comparison.get("paired_case_ids", [])),
            "paired_planned": len(panel.get("cases", [])),
            "sim_pod": config.get("sim_pod", "unknown"),
            "policy_pod": config.get("policy_pod", "unknown"),
            "error_count": len(errors),
            "provider": config.get("codex_provider", "pending"),
            "run_note": run_note,
            "invalid_attempts": len(invalid_attempts),
        },
        "cost": cost_summary(root, history_roots),
        "astra": {
            "label": "Astra + StarVLA",
            "method": "qwenpi_v3_plus_gpt",
            **method_stats(root, panel, outcomes, "qwenpi_v3_plus_gpt"),
        },
        "simulator": {
            "label": "StarVLA / QwenPI_v3",
            "method": "qwenpi_v3",
            **method_stats(root, panel, outcomes, "qwenpi_v3"),
        },
        "policy": {
            "latest": latest,
            "latest_error": latest_error,
            "log_tail": log_lines,
        },
        "results": result_table(panel, outcomes),
        "gpt_timeline": timeline[:30],
        "task_views": views,
        "task_order": list(views),
        "active_runs": active_runs(root, outcomes),
        "video": video,
        "task": {
            "name": current_case.get("task", "等待任务"),
            "case_id": current_case.get("case_id", ""),
            "variant": current_case.get("variant", ""),
            "layout_id": current_case.get("layout_id", ""),
            "eval_seed": current_case.get("eval_seed", ""),
            "tasks": sorted({case.get("task", "") for case in panel.get("cases", [])}),
            "errors": errors[-8:],
        },
    }


def _add_numeric_fields(left: dict, right: dict):
    """Add numeric counters while preserving descriptive pricing metadata."""
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            merged[key] = merged.get(key, 0) + value
    return merged


def _merge_result_tables(primary: dict, additional: dict):
    methods = list(dict.fromkeys(primary.get("methods", []) + additional.get("methods", [])))
    rows = {row.get("task"): dict(row) for row in primary.get("rows", [])}
    order = [row.get("task") for row in primary.get("rows", [])]
    for row in additional.get("rows", []):
        task = row.get("task")
        if task not in rows:
            rows[task] = dict(row)
            order.append(task)
        rows[task].setdefault("methods", {}).update(row.get("methods", {}))
    overall = dict(primary.get("overall", {}))
    overall.setdefault("methods", {}).update(additional.get("overall", {}).get("methods", {}))
    return {"methods": methods, "rows": [rows[task] for task in order], "overall": overall}


def collect_combined(root: Path, additional_roots=(), history_roots=HISTORY_ROOTS):
    """Collect one dashboard state across disjoint, immutable campaigns."""
    state = collect(root, history_roots)
    for additional_root in additional_roots:
        extra = collect(additional_root, ())
        state["root"] += " + " + str(additional_root)
        state["evidence_roots"] = list(
            dict.fromkeys(state.get("evidence_roots", []) + extra.get("evidence_roots", []))
        )
        status = state["status"]
        extra_status = extra["status"]
        for key in ("valid", "planned", "error_count", "invalid_attempts"):
            status[key] = status.get(key, 0) + extra_status.get(key, 0)
        status["finished"] = status.get("finished", False) and extra_status.get(
            "finished", False
        )
        if "INCOMPLETE" in (status.get("state", "") + extra_status.get("state", "")):
            status["state"] = "DRAINING / INCOMPLETE"
        elif not status["finished"]:
            status["state"] = "RUNNING"
        else:
            status["state"] = "COMPLETE"
        status["sim_pod"] = " + ".join(
            dict.fromkeys((status.get("sim_pod"), extra_status.get("sim_pod")))
        )
        status["policy_pod"] = " + ".join(
            dict.fromkeys((status.get("policy_pod"), extra_status.get("policy_pod")))
        )
        status["provider"] = " + ".join(
            dict.fromkeys((status.get("provider"), extra_status.get("provider")))
        )
        status["run_note"] = "两批正式评测并行推进；pending 不计作失败。"

        for section in ("current_campaign", "retained_development", "combined"):
            state["cost"][section] = _add_numeric_fields(
                state["cost"].get(section, {}), extra["cost"].get(section, {})
            )
        state["results"] = _merge_result_tables(state["results"], extra["results"])
        state["direct"] = {
            "label": "GPT-6 Astra Direct",
            "method": "gpt_direct",
            **method_stats(
                additional_root,
                read_json(additional_root / "panel.json", {}) or {},
                read_json(additional_root / "outcomes.json", []) or [],
                "gpt_direct",
            ),
        }
        state["active_runs"].extend(extra.get("active_runs", []))
        for task, extra_view in extra.get("task_views", {}).items():
            if task not in state["task_views"]:
                state["task_views"][task] = extra_view
                state["task_order"].append(task)
                continue
            view = state["task_views"][task]
            view.setdefault("results", {}).setdefault("methods", {}).update(
                extra_view.get("results", {}).get("methods", {})
            )
            view.setdefault("active_runs", []).extend(extra_view.get("active_runs", []))
            view.setdefault("errors", []).extend(extra_view.get("errors", []))
    return state


def write_state(
    asset_dir: Path, root: Path, history_roots=HISTORY_ROOTS, additional_roots=()
):
    state = collect_combined(root, additional_roots, history_roots)
    target = asset_dir / "state.json"
    temporary = asset_dir / ".state.json.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, target)


def updater(
    asset_dir: Path,
    root: Path,
    interval: float,
    history_roots=HISTORY_ROOTS,
    additional_roots=(),
):
    while True:
        try:
            write_state(asset_dir, root, history_roots, additional_roots)
        except Exception as error:  # keep the dashboard alive across partial writes
            fallback = {"generated_at": utc_now(), "monitor_error": repr(error)}
            (asset_dir / "state.json").write_text(json.dumps(fallback, indent=2) + "\n")
        time.sleep(interval)


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve the dashboard plus read-only media files from the campaign root."""

    media_roots = []

    def do_GET(self):  # noqa: N802 - stdlib handler API
        request_path = urlsplit(self.path).path
        if not request_path.startswith("/media/"):
            return super().do_GET()
        relative = unquote(request_path[len("/media/") :]).lstrip("/")
        root_index, separator, relative = relative.partition("/")
        if not separator or not root_index.isdigit() or int(root_index) >= len(self.media_roots):
            self.send_error(404, "unknown media root")
            return
        root = self.media_roots[int(root_index)].resolve()
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self.send_error(403, "media path outside campaign root")
            return
        if not target.is_file():
            self.send_error(404, "media file not found")
            return
        content_type = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
            ".png": "image/png",
            ".jpg": "image/jpeg",
        }.get(target.suffix.lower(), "application/octet-stream")
        try:
            size = target.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with target.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--history-root", action="append", type=Path, default=list(HISTORY_ROOTS))
    parser.add_argument("--additional-root", action="append", type=Path, default=[])
    args = parser.parse_args()
    args.asset_dir.mkdir(parents=True, exist_ok=True)
    write_state(args.asset_dir, args.root, args.history_root, args.additional_root)
    thread = threading.Thread(
        target=updater,
        args=(
            args.asset_dir,
            args.root,
            args.interval,
            args.history_root,
            args.additional_root,
        ),
        daemon=True,
    )
    thread.start()
    media_roots = evidence_roots(
        args.root, read_json(args.root / "outcomes.json", []) or []
    )
    for additional_root in args.additional_root:
        media_roots.extend(
            evidence_roots(
                additional_root,
                read_json(additional_root / "outcomes.json", []) or [],
            )
        )
    DashboardHandler.media_roots = list(dict.fromkeys(media_roots))
    handler = partial(DashboardHandler, directory=str(args.asset_dir))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"StarRoboHarness dashboard: http://{args.host}:{args.port}/dashboard.html", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
