#!/usr/bin/env python3
from __future__ import annotations

import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def _reexec_with_venv() -> None:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def _prepare_qt_environment() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("OUTREACH_AUTOMATION_DISABLE_ONBOARDING", "1")
    os.environ.setdefault("OUTREACH_AUTOMATION_CREDENTIAL_BACKEND", "file")
    os.environ.setdefault(
        "OUTREACH_AUTOMATION_APP_DIR",
        str(Path(tempfile.mkdtemp(prefix="outreach_clickability_doctor_"))),
    )
    pyside_spec = importlib.util.find_spec("PySide6")
    if pyside_spec is None or pyside_spec.origin is None:
        raise RuntimeError("PySide6 is not installed in the active Python environment")
    plugin_path = Path(pyside_spec.origin).parent / "Qt" / "plugins"
    cache_root = Path(tempfile.gettempdir()) / "outreach_clickability_qt_plugins"
    safe_path = cache_root / "plugins"
    if safe_path.exists():
        shutil.rmtree(safe_path)
    safe_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-R", f"{plugin_path}/.", f"{safe_path}/"], check=True)
    os.environ.setdefault("QT_PLUGIN_PATH", str(safe_path))
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(safe_path / "platforms"))


def run_packaged_doctor(app_path: str | None = None) -> int:
    app_bundle = Path(app_path) if app_path else PROJECT_ROOT / "dist" / "Gmail Рассылка.app"
    app_bin = app_bundle / "Contents" / "MacOS" / "Gmail Рассылка"
    if not app_bin.exists():
        print(f"Packaged app binary not found: {app_bin}")
        return 1
    temp_root = Path(tempfile.mkdtemp(prefix="outreach_packaged_clickability_"))
    app_data = temp_root / "Application Support" / "Gmail Рассылка"
    env = os.environ.copy()
    env.update(
        {
            "OUTREACH_AUTOMATION_APP_DIR": str(app_data),
            "OUTREACH_AUTOMATION_CREDENTIAL_BACKEND": "file",
            "OUTREACH_AUTOMATION_DISABLE_ONBOARDING": "1",
            "OUTREACH_AUTOMATION_PACKAGED_CLICKABILITY_DOCTOR": "1",
            "QT_QPA_PLATFORM": env.get("QT_QPA_PLATFORM", "offscreen"),
        }
    )
    result = subprocess.run(
        [str(app_bin)],
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if os.getenv("OUTREACH_KEEP_SMOKE_DATA", "0") != "1":
        shutil.rmtree(temp_root, ignore_errors=True)
    else:
        print(f"Packaged clickability data kept: {temp_root}")
    if result.returncode != 0:
        return result.returncode
    if "PACKAGED_CLICKABILITY_DOCTOR: OK" not in result.stdout:
        print("Packaged clickability doctor did not report OK.")
        return 1
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--packaged":
        app_path = sys.argv[2] if len(sys.argv) >= 3 else None
        return run_packaged_doctor(app_path)

    _reexec_with_venv()
    _prepare_qt_environment()
    sys.path.insert(0, str(PROJECT_ROOT))

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

    from src.campaign_service import CampaignService
    from src.db import Database
    from src.gui.intelligence_views import NewCampaignWizard
    from src.gui.operator_platform import CommandPaletteDialog
    from src.gui.main_window import MainWindow

    class FakeMailer:
        def send_email(self, **kwargs) -> None:
            raise AssertionError("doctor must not send email")

        def check_connection(self, **kwargs):
            return SimpleNamespace(ok=False, message="Введите и сохраните App Password")

    def dialog_ok(*args, **kwargs):
        return QMessageBox.StandardButton.Ok

    QMessageBox.information = dialog_ok
    QMessageBox.warning = dialog_ok
    QMessageBox.critical = dialog_ok
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Cancel

    app = QApplication.instance() or QApplication([])
    tmp_dir = Path(os.environ["OUTREACH_AUTOMATION_APP_DIR"])
    db = Database(tmp_dir / "data" / "doctor.sqlite")
    db.initialize()
    db.set_settings(
        {
            "send_mode": "dry_run",
            "safe_mode": "true",
            "real_send_confirm_required": "true",
            "daily_send_limit": "1",
            "delay_seconds": "0",
            "sender_email": "",
            "allowed_test_recipient": "",
            "onboarding_completed": "true",
        }
    )
    service = CampaignService(
        db,
        mailer=FakeMailer(),
        sleep_fn=lambda _: None,
        export_dir=tmp_dir / "exports",
    )
    window = MainWindow(service)
    window.show()
    app.processEvents()

    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    try:
        window.open_settings()
        settings = window.settings_view
        for field, text, label in (
            (settings.profile_name, "Doctor Gmail", "settings Gmail profile name accepts input"),
            (settings.sender_email, "doctor@example.com", "settings Gmail address accepts input"),
            (settings.app_password, "doctor-app-password", "settings App Password accepts input"),
            (settings.allowed_test_recipient, "owned@example.com", "settings allowed recipient accepts input"),
        ):
            field.clear()
            field.setFocus()
            app.processEvents()
            QTest.keyClicks(field, text)
            check(field.text() == text, label)
        check(settings.app_password.echoMode() == QLineEdit.EchoMode.Password, "App Password is masked")
        settings.ai_provider.setCurrentIndex(settings.ai_provider.findData("openai"))
        settings.ai_model.clear()
        settings.ai_model.setFocus()
        QTest.keyClicks(settings.ai_model, "gpt-4.1-mini")
        settings.ai_api_key.clear()
        settings.ai_api_key.setFocus()
        QTest.keyClicks(settings.ai_api_key, "doctor-openai-key")
        check(settings.ai_model.text() == "gpt-4.1-mini", "AI model accepts input")
        check(settings.ai_api_key.text() == "doctor-openai-key", "AI API key accepts input")
        check(settings.ai_api_key.echoMode() == QLineEdit.EchoMode.Password, "AI API key is masked")
        settings.research_brain_provider.setCurrentIndex(settings.research_brain_provider.findData("openai"))
        settings.research_brain_model.clear()
        settings.research_brain_model.setFocus()
        QTest.keyClicks(settings.research_brain_model, "gpt-4.1-mini")
        settings.research_brain_api_key.clear()
        settings.research_brain_api_key.setFocus()
        QTest.keyClicks(settings.research_brain_api_key, "doctor-research-key")
        settings.writer_brain_provider.setCurrentIndex(settings.writer_brain_provider.findData("openai"))
        settings.writer_brain_model.clear()
        settings.writer_brain_model.setFocus()
        QTest.keyClicks(settings.writer_brain_model, "gpt-4.1-mini")
        settings.writer_brain_api_key.clear()
        settings.writer_brain_api_key.setFocus()
        QTest.keyClicks(settings.writer_brain_api_key, "doctor-writer-key")
        check(settings.research_brain_model.text() == "gpt-4.1-mini", "Research Brain model accepts input")
        check(settings.research_brain_api_key.text() == "doctor-research-key", "Research Brain API key accepts input")
        check(settings.research_brain_api_key.echoMode() == QLineEdit.EchoMode.Password, "Research Brain API key is masked")
        check(settings.writer_brain_model.text() == "gpt-4.1-mini", "Writer Brain model accepts input")
        check(settings.writer_brain_api_key.text() == "doctor-writer-key", "Writer Brain API key accepts input")
        check(settings.writer_brain_api_key.echoMode() == QLineEdit.EchoMode.Password, "Writer Brain API key is masked")
        if settings.telegram_token_input is not None and settings.telegram_default_chat_id_input is not None:
            settings.telegram_token_input.clear()
            settings.telegram_token_input.setFocus()
            QTest.keyClicks(settings.telegram_token_input, "doctor-telegram-token")
            settings.telegram_default_chat_id_input.clear()
            settings.telegram_default_chat_id_input.setFocus()
            QTest.keyClicks(settings.telegram_default_chat_id_input, "1001")
            check(settings.telegram_token_input.text() == "doctor-telegram-token", "Telegram Bot Token accepts input")
            check(settings.telegram_token_input.echoMode() == QLineEdit.EchoMode.Password, "Telegram Bot Token is masked")
            check(settings.telegram_default_chat_id_input.text() == "1001", "Telegram default chat_id accepts input")
        check(settings.add_profile_button.isEnabled(), "Add Gmail profile button enabled")
        check(settings.save_credentials_button.isEnabled(), "Save Gmail button enabled")
        check(settings.set_active_profile_button.isEnabled(), "Set active Gmail profile button enabled")
        check(settings.delete_profile_button.isEnabled(), "Delete Gmail profile button enabled")
        check(settings.check_button.isEnabled(), "Check Gmail button enabled")
        check(settings.save_ai_button.isEnabled(), "Save AI settings button enabled")
        check(settings.check_ai_button.isEnabled(), "Check AI button enabled")
        check(settings.save_research_brain_button.isEnabled(), "Save Research Brain button enabled")
        check(settings.check_research_brain_button.isEnabled(), "Check Research Brain button enabled")
        check(settings.save_writer_brain_button.isEnabled(), "Save Writer Brain button enabled")
        check(settings.check_writer_brain_button.isEnabled(), "Check Writer Brain button enabled")
        if settings.save_telegram_button is not None:
            check(settings.save_telegram_button.isEnabled(), "Save Telegram button enabled")
        if settings.channel_check_buttons.get("telegram") is not None:
            check(settings.channel_check_buttons["telegram"].isEnabled(), "Check Telegram button enabled")
        check(settings.email_sync_now_button.isEnabled(), "Inbox sync button enabled")
        check(settings.telegram_sync_now_button.isEnabled(), "Telegram inbox sync button enabled")
        settings.web_enrichment_max_contacts.setValue(12)
        settings.web_enrichment_max_pages.setValue(2)
        settings.web_enrichment_timeout.setValue(6)
        settings.web_enrichment_cache_ttl.setValue(9)
        settings.web_enrichment_respect_robots.setChecked(True)
        check(settings.web_enrichment_max_contacts.value() == 12, "Web enrichment max contacts control works")
        check(settings.web_enrichment_max_pages.value() == 2, "Web enrichment max pages control works")
        check(settings.web_enrichment_respect_robots.isChecked(), "Web enrichment robots checkbox works")
        settings.inbox_sync_mode.setCurrentIndex(settings.inbox_sync_mode.findData("manual"))
        settings.inbox_sync_interval.setValue(5)
        settings.email_sync_enabled.setChecked(True)
        settings.telegram_sync_enabled.setChecked(True)
        check(settings.inbox_sync_mode.currentData() == "manual", "Inbox sync mode selectable")
        check(settings.inbox_sync_interval.value() >= 5, "Inbox sync interval respects safe minimum")
        QTest.mouseClick(settings.save_credentials_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(service.settings()["sender_email"] == "doctor@example.com", "Save Gmail button persists address")
        check(settings.profile_list.count() >= 1, "Gmail profile list updates after save")
        settings.ai_provider.setCurrentIndex(settings.ai_provider.findData("openai"))
        settings.ai_model.setText("gpt-4.1-mini")
        settings.ai_api_key.setText("doctor-openai-key")
        QTest.mouseClick(settings.save_ai_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(service.settings()["ai_provider"] == "openai", "Save AI settings persists provider")
        settings.research_brain_provider.setCurrentIndex(settings.research_brain_provider.findData("openai"))
        settings.research_brain_model.setText("gpt-4.1-mini")
        settings.research_brain_api_key.setText("doctor-research-key")
        settings.writer_brain_provider.setCurrentIndex(settings.writer_brain_provider.findData("openai"))
        settings.writer_brain_model.setText("gpt-4.1-mini")
        settings.writer_brain_api_key.setText("doctor-writer-key")
        QTest.mouseClick(settings.save_research_brain_button, Qt.MouseButton.LeftButton)
        settings.writer_brain_provider.setCurrentIndex(settings.writer_brain_provider.findData("openai"))
        settings.writer_brain_model.setText("gpt-4.1-mini")
        settings.writer_brain_api_key.setText("doctor-writer-key")
        QTest.mouseClick(settings.save_writer_brain_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(service.settings()["ai_research_provider"] == "openai", "Save Research Brain persists provider")
        check(service.settings()["ai_writer_provider"] == "openai", "Save Writer Brain persists provider")
        QTest.mouseClick(settings.set_active_profile_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(service.active_sender_email() == "doctor@example.com", "Set active Gmail profile button works")
        calls = {"gmail_check": 0}

        def fake_check(**kwargs):
            calls["gmail_check"] += 1
            return SimpleNamespace(ok=False, message="Введите и сохраните App Password")

        settings.service.check_gmail_connection = fake_check
        settings.service.check_ai_connection = lambda **kwargs: SimpleNamespace(ok=False, message="Добавьте API key")
        settings.service.check_ai_brain_connection = lambda *args, **kwargs: SimpleNamespace(ok=False, message="Добавьте Brain API key")
        settings._run_task = lambda task, on_success: on_success(task())
        QTest.mouseClick(settings.check_button, Qt.MouseButton.LeftButton)
        check(calls["gmail_check"] == 1, "Check Gmail button calls connection check")
        QTest.mouseClick(settings.check_ai_button, Qt.MouseButton.LeftButton)
        check(settings.ai_key_status.text(), "Check AI button updates status")
        QTest.mouseClick(settings.check_research_brain_button, Qt.MouseButton.LeftButton)
        check(settings.research_brain_status.text(), "Check Research Brain button updates status")
        QTest.mouseClick(settings.check_writer_brain_button, Qt.MouseButton.LeftButton)
        check(settings.writer_brain_status.text(), "Check Writer Brain button updates status")
        settings.service.check_telegram_connection = lambda **kwargs: SimpleNamespace(ok=False, message="Missing Telegram Bot Token")
        if settings.channel_check_buttons.get("telegram") is not None:
            QTest.mouseClick(settings.channel_check_buttons["telegram"], Qt.MouseButton.LeftButton)
            check(settings.telegram_status_label is not None and settings.telegram_status_label.text(), "Check Telegram button updates status")

        window._select_page(0)
        campaign = window.campaign_view
        check(campaign.sender_selector_button.isEnabled(), "Main sender selector button enabled")
        check(campaign.action_map["campaign.sender_selector"]["slot"] == "open_sender_selector", "Main sender selector is mapped")
        check("doctor@example.com" in campaign.active_sender_label.text(), "Main active sender label shows profile")
        QTest.mouseClick(campaign.ai_mode_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(campaign.ai_mode_button.isChecked(), "Main AI Assist mode button works")
        campaign.ai_generation_mode_combo.setCurrentIndex(campaign.ai_generation_mode_combo.findData("dual_brain"))
        check(campaign.ai_generation_mode_combo.currentData() == "dual_brain", "AI generation mode selector works")
        campaign.web_enrichment_checkbox.setChecked(True)
        check(campaign.web_enrichment_checkbox.isChecked(), "Web enrichment checkbox works")
        check(campaign.enrich_contacts_button.isEnabled(), "Enrich contacts button enabled")
        check(campaign.action_map["campaign.enrich_contacts"]["slot"] == "enrich_contacts", "Enrich contacts action is mapped")
        instagram_index = campaign.channel_selector.findData("instagram")
        campaign.channel_selector.setCurrentIndex(instagram_index)
        app.processEvents()
        manual_index = campaign.execution_mode_combo.findData("manual_assist")
        check(manual_index >= 0, "Manual Assist execution mode available for Instagram")
        check("Ограничения канала" in campaign.execution_risk_label.text(), "Channel limitations label visible")
        campaign.execution_mode_combo.setCurrentIndex(manual_index)
        app.processEvents()
        check(service.execution_mode("instagram") == "manual_assist", "Execution mode selector persists Manual Assist")
        check(campaign.copy_manual_message_button.isEnabled(), "Manual Assist copy button enabled")
        check(campaign.open_manual_profile_button.isEnabled(), "Manual Assist open profile button enabled")
        check(campaign.mark_manual_sent_button.isEnabled(), "Manual Assist mark sent button enabled")
        check(campaign.action_map["campaign.manual_assist_copy"]["slot"] == "copy_manual_message", "Manual Assist copy action mapped")
        email_index = campaign.channel_selector.findData("email")
        campaign.channel_selector.setCurrentIndex(email_index)
        app.processEvents()
        campaign.ai_topic_input.setFocus()
        QTest.keyClicks(campaign.ai_topic_input, "doctor outreach")
        check(campaign.ai_topic_input.text() == "doctor outreach", "AI campaign topic accepts input")
        check(campaign.ai_generate_button.isEnabled(), "AI draft button enabled")
        before_rows = campaign.recipient_preview_table.rowCount()
        QTest.mouseClick(campaign.add_row_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.content_stack.currentIndex() == 0, "Main Add Row stays on main page")
        check(campaign.recipient_preview_table.rowCount() == before_rows + 1, "Main Add Row increases row count")
        row = campaign.recipient_preview_table.rowCount() - 1
        campaign.recipient_preview_table.item(row, 1).setText("main-doctor@example.com")
        campaign.recipient_preview_table.item(row, 2).setText("Doctor subject")
        campaign.recipient_preview_table.item(row, 3).setText("Doctor message")
        QTest.mouseClick(campaign.save_changes_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(service.contacts(window.active_campaign_id())[0]["email"] == "main-doctor@example.com", "Main Save persists row")
        QApplication.clipboard().setText("main-paste-doctor@example.com\tDoctor pasted message")
        QTest.mouseClick(campaign.paste_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(
            any(contact["email"] == "main-paste-doctor@example.com" for contact in service.contacts(window.active_campaign_id())),
            "Main Paste persists clipboard row",
        )
        check(window.content_stack.currentIndex() == 0, "Main Paste stays on main page")

        window._select_page(1)
        contacts = window.contacts_view
        QTest.mouseClick(contacts.add_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(contacts.table.rowCount() >= 1, "Recipients Add Row works")
        contacts.search_input.setFocus()
        QTest.keyClicks(contacts.search_input, "doctor")
        check(contacts.search_input.text() == "doctor", "Recipients search accepts input")
        check(contacts.save_button.isEnabled(), "Recipients Save button enabled")
        check(contacts.delete_button.isEnabled(), "Recipients Delete button enabled")

        qa_rows = []
        for index in range(100):
            channel = ["email", "telegram", "instagram", "x", "tiktok", "vk"][index % 6]
            row = {
                "channel": channel,
                "email": f"doctor-qa-{index:03d}@example.invalid" if channel == "email" else "",
                "handle": f"doctor_qa_{channel}_{index:03d}" if channel != "email" else "",
                "external_id": f"doctor-chat-{index:03d}" if channel == "telegram" else "",
                "profile_url": f"https://example.com/{channel}/doctor-{index:03d}" if channel not in {"email", "telegram"} else "",
                "generated_message": "Doctor QA synthetic outreach draft.",
                "status": "pending_review" if index % 2 else "approved",
            }
            qa_rows.append(row)
        service.add_contact_rows(window.active_campaign_id(), qa_rows, source="ui_clickability_doctor")
        for contact in service.contacts(window.active_campaign_id())[:100]:
            service.update_contact(
                int(contact["id"]),
                {
                    "ai_generated": 1,
                    "ai_confidence": 0.8 if int(contact["id"]) % 3 else 0.3,
                    "lead_status": "Warm" if int(contact["id"]) % 4 == 0 else "New",
                },
            )

        window.refresh_all()
        check(len(window.intelligence_sidebar_buttons) >= 12, "Intelligence sidebar buttons exist")
        intelligence_labels = "\n".join(button.text() for button in window.intelligence_sidebar_buttons)
        check("Кампании" in intelligence_labels, "Campaign intelligence sidebar item exists")
        check("Outreach Session" in intelligence_labels, "Outreach Session sidebar item exists")
        check("Каналы" in intelligence_labels, "Channel cockpit sidebar item exists")
        check("Готовность каналов" in intelligence_labels, "Channel readiness sidebar item exists")
        check("Поиск" in intelligence_labels, "Global search sidebar item exists")
        check("Уведомления" in intelligence_labels, "Notification center sidebar item exists")
        check("Задачи" in intelligence_labels, "Background task monitor sidebar item exists")
        check("Входящие" in intelligence_labels, "Unified inbox sidebar item exists")
        check("Ответы" in intelligence_labels, "Reply inbox sidebar item exists")
        check("Аналитика" in intelligence_labels, "Analytics sidebar item exists")
        check("Performance" in intelligence_labels, "Performance sidebar item exists")
        check(window.command_palette_shortcut.objectName() == "commandPaletteShortcut", "Cmd+K command palette shortcut registered")
        check(window.command_palette_shortcut_ctrl.objectName() == "commandPaletteShortcutCtrl", "Ctrl+K command palette shortcut registered")
        palette = CommandPaletteDialog(service, window.active_campaign_id(), window)
        palette.input.setText("doctor")
        app.processEvents()
        check(palette.input.objectName() == "commandPaletteInput", "Command palette input exists")
        check(palette.table.rowCount() >= 1, "Command palette returns results")
        palette.table.selectRow(0)
        palette.run_selected()
        check(palette.result is not None and palette.result.get("autosend") is False, "Command palette command is safe")
        palette.close()
        QTest.mouseClick(window.intelligence_sidebar_buttons[0], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.campaign_dashboard_view.events_table.objectName() == "campaignTimelineTable", "Campaign dashboard timeline exists")
        check(window.campaign_dashboard_view.preset_selector.count() >= 5, "Campaign preset selector has default presets")
        check(window.campaign_dashboard_view.new_campaign_button.isEnabled(), "New Campaign wizard button enabled")
        check(window.campaign_dashboard_view.apply_preset_button.isEnabled(), "Apply preset button enabled")
        check(window.campaign_dashboard_view.quick_email_button.isEnabled(), "Quick Email Outreach button enabled")
        check(window.campaign_dashboard_view.quick_telegram_button.isEnabled(), "Quick Telegram Campaign button enabled")
        check(window.campaign_dashboard_view.quick_ai_button.isEnabled(), "Quick AI Draft Generation button enabled")
        check(window.campaign_dashboard_view.validation_table.objectName() == "campaignValidationTable", "Campaign validation panel exists")
        check(window.campaign_dashboard_view.health_badge.objectName() == "campaignHealthBadge", "Campaign health badge exists")
        check(window.campaign_dashboard_view.operator_cards["drafts_pending_review"].text() != "", "Operator dashboard widgets render")
        wizard = NewCampaignWizard(service)
        wizard.next_step()
        check(wizard.step_index == 1, "New Campaign wizard Next works")
        wizard.previous_step()
        check(wizard.step_index == 0, "New Campaign wizard Back works")
        check(wizard.preset_selector.count() >= 5, "New Campaign wizard preset selector works")
        check(wizard.execution_selector.count() >= 1, "New Campaign wizard execution selector works")
        wizard.close()
        QTest.mouseClick(window.intelligence_sidebar_buttons[1], Qt.MouseButton.LeftButton)
        app.processEvents()
        session = window.outreach_session_view
        check(session.mode_selector.objectName() == "operatorModeSelector", "Operator mode selector exists")
        check(session.batch_order_selector.objectName() == "sessionBatchOrderSelector", "Session batch order selector exists")
        check(session.start_session_button.isEnabled(), "Start Outreach Session button enabled")
        check(session.restore_session_button.isEnabled(), "Restore Outreach Session button enabled")
        check(session.focus_mode_toggle.objectName() == "sessionFocusModeToggle", "Focus Mode toggle exists")
        check(session.quick_review_toggle.objectName() == "quickReviewModeToggle", "Quick Review mode toggle exists")
        check(session.hotkey_helper.text(), "Session hotkey helper visible")
        check(len(session.hotkey_shortcuts) >= 23, "Session hotkeys registered")
        check("J" in session.hotkey_shortcuts and "K" in session.hotkey_shortcuts, "J/K lead navigation hotkeys registered")
        check("E" in session.hotkey_shortcuts, "E edit hotkey registered")
        check(session.copy_button.isEnabled(), "Session copy button enabled")
        check(session.open_profile_button.isEnabled(), "Session open profile button enabled")
        check(session.mark_sent_button.isEnabled(), "Session mark sent button enabled")
        check(session.skip_button.isEnabled(), "Session skip button enabled")
        check(session.needs_review_filter.objectName() == "sessionNeedsReviewFilter", "Session needs-review filter exists")
        check(session.ready_filter.objectName() == "sessionReadyToSendFilter", "Session ready filter exists")
        check(session.manual_assist_filter.objectName() == "sessionManualAssistFilter", "Session manual-assist filter exists")
        check(session.low_confidence_filter.objectName() == "sessionLowConfidenceFilter", "Session low-confidence filter exists")
        check(session.tiktok_filter.objectName() == "sessionTikTokOnly", "Session TikTok filter exists")
        check(session.x_filter.objectName() == "sessionXOnly", "Session X filter exists")
        check(session.vk_filter.objectName() == "sessionVKOnly", "Session VK filter exists")
        session.focus_mode_toggle.setChecked(True)
        app.processEvents()
        check(not session.filters_widget.isVisible(), "Focus Mode hides filter clutter")
        session.focus_mode_toggle.setChecked(False)
        app.processEvents()
        session.quick_review_toggle.setChecked(True)
        app.processEvents()
        check(not session.filters_widget.isVisible(), "Quick Review hides filter clutter")
        session.quick_review_toggle.setChecked(False)
        app.processEvents()
        session.batch_order_selector.setCurrentIndex(session.batch_order_selector.findData("ai_confidence"))
        check(session.batch_order_selector.currentData() == "ai_confidence", "Session batch order selector changes")
        session.search_input.setFocus()
        QTest.keyClicks(session.search_input, "doctor")
        check(session.search_input.text() == "doctor", "Session search accepts input")
        session.search_input.clear()
        QTest.mouseClick(session.start_session_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(session.current_session_id is not None, "Outreach Session starts/restores session")
        check((session.current_snapshot or {}).get("total", 0) >= 100, "100 lead Outreach Session loads")
        session.draft_editor.setFocus()
        before_contact = session.current_contact_id
        QTest.keyClick(session.draft_editor, Qt.Key.Key_N)
        app.processEvents()
        check(session.current_contact_id == before_contact, "Single-key hotkeys ignored while editing")
        session.draft_editor.clearFocus()
        QTest.keyClick(session, Qt.Key.Key_Space)
        app.processEvents()
        check(session.current_contact_id != before_contact, "Space hotkey advances when not editing")
        QTest.mouseClick(session.restore_session_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(session.current_session_id is not None, "Outreach Session restore button works")
        QTest.mouseClick(window.intelligence_sidebar_buttons[2], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.ai_assist_view.score_button.isEnabled(), "AI scoring button enabled")
        check(window.ai_assist_view.preset_selector.count() >= 1, "Campaign presets visible")
        QTest.mouseClick(window.intelligence_sidebar_buttons[3], Qt.MouseButton.LeftButton)
        app.processEvents()
        cockpit = window.channel_cockpit_view
        check(cockpit.channel_selector.count() >= 8, "Channel cockpit selector has connector slots")
        check(cockpit.copy_button.isEnabled(), "Channel cockpit copy button enabled")
        check(cockpit.open_profile_button.isEnabled(), "Channel cockpit open profile button enabled")
        check(cockpit.mark_sent_button.isEnabled(), "Channel cockpit mark sent button enabled")
        check(cockpit.export_csv_button.isEnabled(), "Channel cockpit CSV export enabled")
        check(cockpit.export_json_button.isEnabled(), "Channel cockpit JSON export enabled")
        for channel in ("instagram", "tiktok", "x", "vk"):
            index = cockpit.channel_selector.findData(channel)
            cockpit.channel_selector.setCurrentIndex(index)
            app.processEvents()
            check(cockpit.workflow_table.rowCount() >= 3, f"{channel} cockpit workflow renders")
            check(cockpit.message_preview.isEnabled(), f"{channel} cockpit message preview enabled")
        QTest.mouseClick(cockpit.copy_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(QApplication.clipboard().text() != "", "Channel cockpit copy action works")
        QTest.mouseClick(window.intelligence_sidebar_buttons[4], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.channel_readiness_view.table.rowCount() >= 8, "Channel readiness matrix renders")
        check(window.channel_readiness_view.refresh_button.isEnabled(), "Channel readiness refresh button enabled")
        QTest.mouseClick(window.intelligence_sidebar_buttons[5], Qt.MouseButton.LeftButton)
        app.processEvents()
        search = window.global_search_view
        check(search.recent_selector.objectName() == "globalSearchRecentSelector", "Global search recent selector exists")
        search.search_input.setFocus()
        QTest.keyClicks(search.search_input, "doctor")
        QTest.mouseClick(search.search_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(search.results_table.rowCount() >= 1, "Global search returns history results")
        check(search.open_button.isEnabled(), "Global search open button enabled")
        QTest.mouseClick(window.intelligence_sidebar_buttons[6], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.notification_center_view.table.objectName() == "notificationCenterTable", "Notification center table exists")
        check(window.notification_center_view.refresh_button.isEnabled(), "Notification center refresh button enabled")
        QTest.mouseClick(window.intelligence_sidebar_buttons[7], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.background_task_monitor_view.table.objectName() == "taskMonitorTable", "Background task monitor table exists")
        check(window.background_task_monitor_view.refresh_button.isEnabled(), "Background task monitor refresh button enabled")
        QTest.mouseClick(window.intelligence_sidebar_buttons[8], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.unified_inbox_view.conversation_list.objectName() == "inboxConversationList", "Unified inbox conversation list exists")
        check(window.unified_inbox_view.thread_table.objectName() == "conversationThreadTable", "Conversation thread panel exists")
        check(window.unified_inbox_view.sync_now_button.isEnabled(), "Inbox sync now button enabled")
        check(window.unified_inbox_view.refresh_inbox_button.isEnabled(), "Inbox refresh button enabled")
        check(window.unified_inbox_view.open_conversation_button.isEnabled(), "Open conversation button enabled")
        check(window.unified_inbox_view.copy_reply_button.isEnabled(), "Inbox copy reply button enabled")
        check(window.unified_inbox_view.open_profile_button.isEnabled(), "Inbox open profile button enabled")
        check(window.unified_inbox_view.mark_replied_manual_button.isEnabled(), "Inbox mark replied manually button enabled")
        check(window.unified_inbox_view.mark_followup_done_button.isEnabled(), "Inbox mark follow-up done button enabled")
        window.unified_inbox_view.reply_composer.setFocus()
        QTest.keyClicks(window.unified_inbox_view.reply_composer, "doctor inbox reply")
        check("doctor inbox reply" in window.unified_inbox_view.reply_composer.toPlainText(), "Reply composer accepts text")
        QTest.mouseClick(window.unified_inbox_view.copy_reply_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(QApplication.clipboard().text() == window.unified_inbox_view.reply_composer.toPlainText(), "Inbox copy reply action copies text")
        QTest.mouseClick(window.unified_inbox_view.suggest_reply_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.unified_inbox_view.feedback_label.text(), "Inbox AI reply suggestion callable")
        QTest.mouseClick(window.unified_inbox_view.suggest_followup_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.unified_inbox_view.feedback_label.text(), "Inbox follow-up suggestion callable")
        QTest.mouseClick(window.intelligence_sidebar_buttons[9], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.reply_inbox_view.add_reply_button.isEnabled(), "Add reply button enabled")
        window.reply_inbox_view.reply_text.setFocus()
        QTest.keyClicks(window.reply_inbox_view.reply_text, "doctor reply")
        check("doctor reply" in window.reply_inbox_view.reply_text.toPlainText(), "Reply input accepts text")
        QTest.mouseClick(window.reply_inbox_view.suggest_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.reply_inbox_view.suggestion_label.text(), "AI reply suggestions callable")
        QTest.mouseClick(window.intelligence_sidebar_buttons[10], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.analytics_view.refresh_button.isEnabled(), "Analytics refresh button enabled")
        QTest.mouseClick(window.intelligence_sidebar_buttons[11], Qt.MouseButton.LeftButton)
        app.processEvents()
        check(window.performance_platform_view.table.objectName() == "performanceSnapshotTable", "Performance snapshot table exists")
        check(window.performance_platform_view.refresh_button.isEnabled(), "Performance refresh button enabled")

        window.open_settings()
        app.processEvents()
        focus_fields = [settings.profile_name, settings.sender_email, settings.app_password, settings.allowed_test_recipient]
        if settings.telegram_token_input is not None:
            focus_fields.append(settings.telegram_token_input)
        if settings.telegram_default_chat_id_input is not None:
            focus_fields.append(settings.telegram_default_chat_id_input)
        for field in focus_fields:
            center = field.mapTo(window, field.rect().center())
            top_widget = window.childAt(center)
            field.setFocus()
            check(field.hasFocus(), f"{field.objectName()} accepts focus")
            if top_widget is not None:
                check(
                    top_widget is field or field.isAncestorOf(top_widget),
                    f"{field.objectName()} is not covered by an overlay",
                )
    finally:
        window.campaign_view.shutdown()
        window.settings_view.shutdown()
        window.close()
        app.processEvents()

    print(f"UI clickability doctor: OK ({len(checks)} checks)")
    for label in checks:
        print(f"- {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
