from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.db import Database
from src.excel_importer import ContactImporter


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    return db


def write_workbook(path: Path, rows: list[list[str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_import_valid_excel(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    path = tmp_path / "contacts.xlsx"
    write_workbook(
        path,
        [
            ["Email", "Name", "Company", "Topic", "Subject", "Message"],
            ["alex@example.com", "Alex", "Acme", "B2B", "Hello", "Base text"],
        ],
    )

    result = ContactImporter(db).import_file(path, campaign_id)
    contacts = db.list_contacts(campaign_id)

    assert result.imported_count == 1
    assert result.skipped_count == 0
    assert contacts[0]["email"] == "alex@example.com"
    assert contacts[0]["status"] == "new"


def test_invalid_emails_are_skipped(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    path = tmp_path / "contacts.xlsx"
    write_workbook(
        path,
        [
            ["почта", "имя"],
            ["not-an-email", "Broken"],
            ["", "Empty"],
            ["valid@example.com", "Valid"],
        ],
    )

    result = ContactImporter(db).import_file(path, campaign_id)

    assert result.imported_count == 1
    assert result.skipped_count == 2
    assert len(db.recent_import_errors()) == 2


def test_duplicate_emails_are_not_imported_twice(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    campaign_id = db.get_default_campaign_id()
    path = tmp_path / "contacts.xlsx"
    write_workbook(
        path,
        [
            ["email", "name"],
            ["dupe@example.com", "One"],
            ["DUPE@example.com", "Two"],
        ],
    )

    result = ContactImporter(db).import_file(path, campaign_id)

    assert result.imported_count == 1
    assert result.skipped_count == 1
    assert len(db.list_contacts(campaign_id)) == 1
