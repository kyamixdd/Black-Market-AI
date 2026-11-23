"""Versioned deterministic benchmark for assistant outcome quality.

Run from the repository root:
    python -m benchmarks.assistant_outcomes.evaluate --report benchmarks/assistant_outcomes/reports/v1.0.0.json

Promotion checks compare a candidate report to an explicit baseline. A benchmark run
without a baseline measures behavior but does not claim improvement.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src_tauri.backend.assistant_nlu import parse_assistant_request
from src_tauri.backend.assistant_tool_registry import create_default_registry
from src_tauri.backend.assistant_memory import retrieve_relevant_memories
from src_tauri.backend.assistant_runtime import execute_assistant_query


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "benchmarks" / "assistant_outcomes" / "dataset-v1.json"


class MemoryRepository:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.items = [
            {**item, "updated_at": now, "owner_key": "benchmark-owner"}
            for item in items
        ]

    def retrieve_assistant_memories(self, owner_key: str, *, limit: int) -> list[dict[str, Any]]:
        return [dict(item) for item in self.items if item["owner_key"] == owner_key][:limit]


class BenchmarkBridge:
    def get_market_snapshot(self, symbol: str, market: str) -> dict[str, Any]:
        return {
            "symbol": symbol, "market": market, "price": 100.0,
            "price_change_24h": 0.5, "regime": "UNKNOWN",
            "data_freshness": "FRESH", "data_age_seconds": 0,
        }

    def get_risk_metrics(self) -> dict[str, Any]:
        return {"exposure": 0.0, "risk_status": "within_limits"}


def _ratio(correct: int, total: int) -> float:
    return round(correct / total, 4) if total else 0.0


async def evaluate(dataset: dict[str, Any]) -> dict[str, Any]:
    intent_correct = 0
    intent_results = []
    for case in dataset["intent_cases"]:
        parsed = parse_assistant_request(case["query"])
        actual_tools = sorted({intent.tool for intent in parsed.intents})
        expected_tools = sorted(case["expected_tools"])
        correct = actual_tools == expected_tools
        intent_correct += int(correct)
        intent_results.append({
            "id": case["id"], "pass": correct,
            "expected_tools": expected_tools, "actual_tools": actual_tools,
            "confidence": parsed.confidence.value,
            "unsupported": parsed.unsupported,
        })

    registry = create_default_registry()
    specs = {item["tool_id"]: item for item in registry.list_tools()}
    expected_tool_ids = sorted({tool for case in dataset["intent_cases"] for tool in case["expected_tools"]})
    tool_checks = []
    for tool_id in expected_tool_ids:
        spec = specs.get(tool_id)
        safe = bool(spec and spec["available"] and spec["read_only"] and not spec["changes_state"])
        tool_checks.append({"tool_id": tool_id, "pass": safe, "registered": spec is not None,
                            "read_only": bool(spec and spec["read_only"]),
                            "changes_state": bool(spec and spec["changes_state"])})
    tool_correct = sum(int(item["pass"]) for item in tool_checks)

    memory_correct = 0
    memory_results = []
    for case in dataset["memory_cases"]:
        repo = MemoryRepository(case["memories"])
        retrieved = retrieve_relevant_memories(repo, "benchmark-owner", case["query"], limit=3)
        actual_ids = [item["memory_id"] for item in retrieved]
        expected_ids = case["expected_top_ids"]
        correct = bool(actual_ids and actual_ids[0] in expected_ids)
        memory_correct += int(correct)
        memory_results.append({"id": case["id"], "pass": correct,
                               "expected_top_ids": expected_ids, "actual_top_ids": actual_ids})

    completion_correct = 0
    completion_results = []
    bridge = BenchmarkBridge()
    for case in dataset["completion_cases"]:
        result = await execute_assistant_query(
            bridge, case["query"], "BTCUSDT", "SPOT", "1h"
        )
        correct = (result.task_state == case["expected_state"] and
                   result.status == case["expected_status"])
        completion_correct += int(correct)
        completion_results.append({
            "id": case["id"], "pass": correct,
            "expected_state": case["expected_state"], "actual_state": result.task_state,
            "expected_status": case["expected_status"], "actual_status": result.status,
            "tool": result.tool,
        })

    metrics = {
        "intent_exact_match": _ratio(intent_correct, len(intent_results)),
        "tool_registry_safety": _ratio(tool_correct, len(tool_checks)),
        "memory_top1_relevance": _ratio(memory_correct, len(memory_results)),
        "completion_accuracy": _ratio(completion_correct, len(completion_results)),
    }
    return {
        "report_version": "1.0.0",
        "benchmark_id": dataset["benchmark_id"],
        "dataset_version": dataset["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_status": "measured",
        "sample_counts": {
            "intent": len(intent_results), "tools": len(tool_checks),
            "memory": len(memory_results), "completion": len(completion_results),
        },
        "metrics": metrics,
        "details": {
            "intent": intent_results, "tools": tool_checks,
            "memory": memory_results, "completion": completion_results,
        },
    }


def promotion_gate(candidate: dict[str, Any], baseline: dict[str, Any] | None,
                   policy: dict[str, Any]) -> dict[str, Any]:
    if baseline is None:
        return {"eligible": False, "reason": "No measured baseline supplied; measurement alone cannot establish improvement."}
    thresholds = {
        "intent_exact_match": policy["minimum_intent_exact_match"],
        "tool_registry_safety": policy["minimum_tool_registry_safety"],
        "memory_top1_relevance": policy["minimum_memory_top1_relevance"],
        "completion_accuracy": policy["minimum_completion_accuracy"],
    }
    checks = {}
    for metric, minimum in thresholds.items():
        value = candidate["metrics"].get(metric, 0.0)
        previous = baseline["metrics"].get(metric, 0.0)
        checks[metric] = {
            "candidate": value, "baseline": previous, "minimum": minimum,
            "passes_minimum": value >= minimum,
            "no_regression": value >= previous,
        }
    eligible = all(item["passes_minimum"] for item in checks.values())
    if policy.get("no_metric_regression", True):
        eligible = eligible and all(item["no_regression"] for item in checks.values())
    return {"eligible": eligible, "checks": checks,
            "reason": "Promotion requires all thresholds and configured non-regression checks."}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--report", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--enforce-promotion", action="store_true")
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    report = asyncio.run(evaluate(dataset))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
    report["promotion"] = promotion_gate(report, baseline, dataset["promotion_policy"])
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_version": report["report_version"],
                     "dataset_version": report["dataset_version"],
                     "metrics": report["metrics"],
                     "promotion": report["promotion"]}, indent=2))
    if args.enforce_promotion and not report["promotion"]["eligible"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
