#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_operator_qa_data import QA_CAMPAIGN_NAME, generate_operator_qa_data
from src.campaign_service import CampaignService
from src.config import DATA_DIR
from src.db import Database
from src.operator import HIGH_VOLUME_MODE, ReviewQueueFilters


def _measure(label: str, iterations: int, fn: Callable[[], object]) -> dict[str, float | str]:
    timings: list[float] = []
    for _ in range(max(iterations, 1)):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    return {
        "operation": label,
        "average_ms": round(statistics.mean(timings), 2),
        "p95_ms": round(_p95(timings), 2),
        "slowest_ms": round(max(timings), 2),
    }


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index]


def _service(db_path: Path) -> CampaignService:
    db = Database(db_path)
    db.initialize()
    return CampaignService(db, sleep_fn=lambda _: None, export_dir=Path(tempfile.gettempdir()) / "outreach_operator_benchmark_exports")


def run_benchmark(*, count: int = 100, db_path: str | None = None, reset: bool = False) -> list[dict[str, float | str]]:
    target_db = Path(db_path).expanduser() if db_path else DATA_DIR / "outreach.sqlite"
    result = generate_operator_qa_data(count=count, reset=reset, db_path=str(target_db))
    service = _service(target_db)
    campaign_id = int(result["campaign_id"])
    campaign = service.db.fetch_one("SELECT id FROM campaigns WHERE name = ? ORDER BY id DESC LIMIT 1", (QA_CAMPAIGN_NAME,))
    if campaign:
        campaign_id = int(campaign["id"])

    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(snapshot["session"]["id"])
    current_id = int(snapshot["current"]["contact"]["id"]) if snapshot.get("current") else 0

    measurements = [
        _measure("load 100 leads", 5, lambda: service.operator_review_queue(campaign_id)),
        _measure("next lead", 30, lambda: service.operator_move_session(session_id, direction="next")),
        _measure("copy message", 30, lambda: service.operator_copy_message(session_id, current_id)),
        _measure(
            "filter high priority",
            10,
            lambda: service.operator_review_queue(campaign_id, ReviewQueueFilters(only_high_priority=True)),
        ),
        _measure("search", 10, lambda: service.operator_global_search(campaign_id, "QA Studio")),
        _measure("session restore", 20, lambda: service.restore_outreach_session(campaign_id)),
    ]
    mark_ids = [
        int(item["contact"]["id"])
        for item in service.operator_review_queue(campaign_id)[:5]
    ]

    def mark_one() -> None:
        if mark_ids:
            contact_id = mark_ids.pop(0)
            service.operator_mark_manually_sent(session_id, contact_id)

    measurements.append(_measure("mark sent", 5, mark_one))
    return measurements


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Outreach Session operator throughput on synthetic data.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    measurements = run_benchmark(count=max(args.count, 100), db_path=args.db_path or None, reset=args.reset)
    print("Operator throughput benchmark (synthetic data, no real sends)")
    for row in measurements:
        print(
            f"- {row['operation']}: avg={row['average_ms']}ms "
            f"p95={row['p95_ms']}ms slowest={row['slowest_ms']}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
