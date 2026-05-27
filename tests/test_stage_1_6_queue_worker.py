from __future__ import annotations

from pathlib import Path

from src.background_worker import QueueJobProcessor
from src.campaign_service import CampaignService
from src.db import Database
from src.queue_service import QueueService
from src.state_machine import can_transition, get_allowed_transitions, transition_contact


class FakeMailer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, object]] = []

    def send_email(self, **kwargs) -> None:
        self.sent.append(kwargs)
        if self.fail:
            raise RuntimeError("fake smtp failure")


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "outreach.sqlite")
    db.initialize()
    db.set_settings(
        {
            "sender_email": "sender@example.com",
            "daily_send_limit": "25",
            "delay_seconds": "0",
            "safe_mode": "true",
            "send_mode": "dry_run",
            "real_send_confirm_required": "true",
        }
    )
    return db


def add_contact(db: Database, campaign_id: int, status: str, email: str = "lead@example.com") -> int:
    contact_id = db.add_contact(
        {
            "campaign_id": campaign_id,
            "email": email,
            "name": "Lead",
            "company": "Lead Co",
            "topic": "Queue",
            "subject": "Hello",
            "base_message": "Base",
            "status": "new",
        }
    )
    db.update_contact(contact_id, {"status": status, "generated_message": "Generated"})
    return contact_id


def test_state_machine_valid_invalid_and_blacklist_override(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "new")

    assert can_transition("new", "generation_queued")
    assert not can_transition("queued", "pending_review")
    assert "blacklisted" in get_allowed_transitions("sent")

    assert transition_contact(db, contact_id, "generation_queued").ok
    invalid = transition_contact(db, contact_id, "sent")
    assert not invalid.ok
    assert "Invalid contact transition" in invalid.error
    assert transition_contact(db, contact_id, "blacklisted").ok
    assert not transition_contact(db, contact_id, "sent").ok


def test_queue_enqueue_only_approved_contacts_for_send(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    approved_id = add_contact(db, campaign_id, "approved", "approved@example.com")
    add_contact(db, campaign_id, "pending_review", "pending@example.com")
    queue = QueueService(db)

    result = queue.enqueue_bulk_send(campaign_id, mode="dry_run")
    jobs = queue.list_recent_jobs(campaign_id)

    assert result.count == 1
    assert len(jobs) == 1
    assert jobs[0]["contact_id"] == approved_id
    assert db.get_contact(approved_id)["status"] == "queued"


def test_retry_failed_job_and_cancel_job(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "approved")
    queue = QueueService(db)
    queued = queue.enqueue_bulk_send(campaign_id, mode="dry_run")
    job = queue.list_recent_jobs(campaign_id)[0]

    queue.fail_job(job["id"], "boom")
    db.update_contact(contact_id, {"status": "failed"})
    retry = queue.retry_failed_job(job["id"])
    assert retry.ok
    assert db.get_contact(contact_id)["status"] == "queued"

    cancel = queue.cancel_job(job["id"])
    assert cancel.ok
    assert db.fetch_one("SELECT status FROM job_queue WHERE id = ?", (job["id"],))["status"] == "cancelled"
    assert queued.count == 1


def test_worker_survives_exception_and_continues_next_job(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    bad_id = add_contact(db, campaign_id, "approved", "bad@example.com")
    good_id = add_contact(db, campaign_id, "approved", "good@example.com")
    queue = QueueService(db)
    queue.enqueue_bulk_send(campaign_id, mode="dry_run")
    db.update_contact(bad_id, {"status": "sent"})
    processor = QueueJobProcessor(CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None), queue)

    processed = processor.process_available()

    assert processed == 2
    assert db.get_contact(good_id)["status"] == "dry_run_sent"
    statuses = {job["status"] for job in queue.list_recent_jobs(campaign_id)}
    assert "failed" in statuses
    assert "completed" in statuses


def test_worker_progress_updates(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "new")
    service = CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None)
    service.enqueue_generate_messages(campaign_id)
    seen: list[tuple[int, int, str]] = []

    QueueJobProcessor(service).process_available(progress_callback=lambda *args: seen.append(args))

    assert seen
    assert max(progress for _, progress, _ in seen) == 100


def test_dry_run_job_does_not_call_smtp(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "approved")
    fake = FakeMailer()
    service = CampaignService(db, mailer=fake, sleep_fn=lambda _: None)
    service.enqueue_send_approved(campaign_id, mode="dry_run")

    QueueJobProcessor(service).process_available()

    assert fake.sent == []
    assert db.get_contact(contact_id)["status"] == "dry_run_sent"
    assert db.fetch_one("SELECT id FROM send_logs WHERE action = 'dry_run_send'") is not None


def test_live_job_blocked_without_confirm(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "approved")
    db.set_settings({"send_mode": "live", "allowed_test_recipient": "lead@example.com"})
    fake = FakeMailer()
    service = CampaignService(db, mailer=fake, sleep_fn=lambda _: None)
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=False)

    QueueJobProcessor(service).process_available()

    assert fake.sent == []
    assert db.get_contact(contact_id)["status"] == "failed"
    assert "explicitly confirms" in db.get_contact(contact_id)["last_error"]


def test_blacklist_blocks_queued_send(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    contact_id = add_contact(db, campaign_id, "approved", "blocked@example.com")
    service = CampaignService(db, mailer=FakeMailer(), sleep_fn=lambda _: None)
    service.blacklist.add("blocked@example.com", "no")
    service.enqueue_send_approved(campaign_id, mode="dry_run")

    QueueJobProcessor(service).process_available()

    assert db.get_contact(contact_id)["status"] == "blacklisted"


def test_daily_limit_blocks_queued_live_send(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "approved", "owned@example.com")
    db.set_settings(
        {
            "send_mode": "live",
            "daily_send_limit": "1",
            "allowed_test_recipient": "owned@example.com",
        }
    )
    db.log_send(None, campaign_id, "live_send", "sent", "")
    fake = FakeMailer()
    service = CampaignService(db, mailer=fake, sleep_fn=lambda _: None)
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True)

    QueueJobProcessor(service).process_available()

    assert fake.sent == []
    job = service.queue.list_recent_jobs(campaign_id)[0]
    assert job["status"] == "failed"
    assert "Remaining today: 0/1" in job["last_error"]


def test_allowed_test_recipient_mismatch_handled(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "approved", "other@example.com")
    db.set_settings(
        {
            "send_mode": "live",
            "allowed_test_recipient": "owned@example.com",
        }
    )
    fake = FakeMailer()
    service = CampaignService(db, mailer=fake, sleep_fn=lambda _: None)
    service.enqueue_send_approved(campaign_id, mode="live", confirm_live_send=True)

    QueueJobProcessor(service).process_available()

    assert fake.sent == []
    job = service.queue.list_recent_jobs(campaign_id)[0]
    assert job["status"] == "failed"
    assert "owned@example.com" in job["last_error"]
    assert "other@example.com" in job["last_error"]


def test_export_report_background_job_creates_report(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    add_contact(db, campaign_id, "approved")
    service = CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_path / "exports",
    )
    service.enqueue_export_report(campaign_id)

    QueueJobProcessor(service).process_available()

    reports = list((tmp_path / "exports").glob("contacts_export_*.xlsx"))
    assert reports
    assert service.queue.list_recent_jobs(campaign_id)[0]["status"] == "completed"
