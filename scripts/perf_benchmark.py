#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.campaign_service import CampaignService
from src.db import Database
from src.operator import HIGH_VOLUME_MODE, ReviewQueueFilters


class BenchmarkMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)
        raise AssertionError("performance benchmark must not send email")

    def check_connection(self, **kwargs):
        return SimpleNamespace(ok=False, message="benchmark uses no live credentials")


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index]


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


def _rows(count: int) -> list[dict[str, object]]:
    channels = ["email", "telegram", "instagram", "x", "tiktok", "vk"]
    rows: list[dict[str, object]] = []
    for index in range(max(count, 1)):
        channel = channels[index % len(channels)]
        rows.append(
            {
                "channel": channel,
                "email": f"perf-{index:05d}@example.invalid" if channel == "email" else "",
                "handle": f"perf_{channel}_{index:05d}" if channel != "email" else "",
                "external_id": f"perf-chat-{index:05d}" if channel == "telegram" else "",
                "profile_url": f"https://example.com/{channel}/perf-{index:05d}" if channel not in {"email", "telegram"} else "",
                "name": f"Perf Lead {index}",
                "company": f"Perf Company {index % 50}",
                "topic": "synthetic performance dataset",
                "generated_message": "Synthetic benchmark message. Operator/manual workflow only.",
                "status": "pending_review" if index % 3 else "approved",
            }
        )
    return rows


def _service(db_path: Path, export_dir: Path) -> CampaignService:
    db = Database(db_path)
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "onboarding_completed": "true",
            "operator_mode": "high_volume",
            "execution_mode_instagram": "manual_assist",
            "execution_mode_tiktok": "manual_assist",
            "execution_mode_x": "manual_assist",
            "execution_mode_vk": "manual_assist",
        }
    )
    return CampaignService(db, mailer=BenchmarkMailer(), sleep_fn=lambda _: None, export_dir=export_dir)


def run_benchmark(*, count: int = 1000, db_path: str | None = None, reset: bool = False) -> list[dict[str, float | str]]:
    temp_root = Path(tempfile.mkdtemp(prefix="outreach_perf_benchmark_"))
    target_db = Path(db_path).expanduser() if db_path else temp_root / "perf.sqlite"
    if reset and target_db.exists():
        target_db.unlink()
    service = _service(target_db, temp_root / "exports")
    campaign_id = service.default_campaign_id()
    rows = _rows(count)

    measurements: list[dict[str, float | str]] = []
    measurements.append(_measure("app startup", 3, lambda: _service(target_db, temp_root / "exports2").settings()))
    measurements.append(_measure("massive import", 1, lambda: service.massive_import_rows(campaign_id, rows, chunk_size=500, source="perf_benchmark")))
    page = service.contacts_page(campaign_id, offset=0, limit=250)
    first_contact_id = int(page["items"][0]["id"]) if page["items"] else 0
    snapshot = service.start_outreach_session(campaign_id, mode=HIGH_VOLUME_MODE)
    session_id = int(snapshot["session"]["id"])

    measurements.extend(
        [
            _measure("lead switching", 40, lambda: service.operator_move_session(session_id, direction="next")),
            _measure("ai render", 25, lambda: service.operator_fast_variants(first_contact_id)),
            _measure("inbox open", 10, lambda: service.unified_inbox(campaign_id=campaign_id)),
            _measure("search", 20, lambda: service.global_search("Perf Company", campaign_id=campaign_id, limit=50)),
            _measure("filter", 10, lambda: service.operator_review_queue(campaign_id, ReviewQueueFilters(manual_assist=True))),
            _measure("session restore", 20, lambda: service.restore_outreach_session(campaign_id)),
            _measure("queue latency", 10, lambda: service.background_task_monitor(campaign_id)),
            _measure("contacts page", 20, lambda: service.contacts_page(campaign_id, offset=250, limit=250)),
        ]
    )
    assert not service.mailer.sent
    return measurements


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 5.0 production operator performance benchmark.")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    rows = run_benchmark(count=max(args.count, 100), db_path=args.db_path or None, reset=args.reset)
    print("Stage 5.0 perf benchmark (synthetic data, no real sends)")
    for row in rows:
        print(
            f"- {row['operation']}: avg={row['average_ms']}ms "
            f"p95={row['p95_ms']}ms slowest={row['slowest_ms']}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
