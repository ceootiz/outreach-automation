from __future__ import annotations

from typing import Any


STATUS_LABELS_RU: dict[str, str] = {
    "all": "Все статусы",
    "new": "Новый",
    "generation_queued": "В очереди подготовки",
    "generating": "Подготовка",
    "pending_review": "Нужно подтвердить",
    "approved": "Подтверждено",
    "queued": "В очереди отправки",
    "sending": "Отправляется",
    "dry_run_sent": "Проверено без отправки",
    "sent": "Отправлено",
    "failed": "Ошибка",
    "blacklisted": "Черный список",
    "cancelled": "Отменено",
}

STATUS_BY_LABEL_RU = {label.lower(): status for status, label in STATUS_LABELS_RU.items()}

SEND_MODE_LABELS_RU = {
    "dry_run": "Тестовый режим",
    "live": "Боевой режим",
}

JOB_TYPE_LABELS_RU = {
    "generate_message": "Подготовка сообщения",
    "ai_generate_draft": "AI-черновик",
    "dry_run_send": "Проверка отправки",
    "live_send": "Отправка Gmail",
    "export_report": "Отчет",
}

JOB_STATUS_LABELS_RU = {
    "pending": "ожидает",
    "queued": "в очереди",
    "running": "выполняется",
    "paused": "пауза",
    "completed": "завершено",
    "failed": "ошибка",
    "cancelled": "отменено",
}


def status_to_ru(status: object) -> str:
    value = "" if status is None else str(status)
    return STATUS_LABELS_RU.get(value, value)


def status_from_ru(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized in STATUS_LABELS_RU:
        return normalized
    return STATUS_BY_LABEL_RU.get(normalized)


def send_mode_to_ru(mode: object) -> str:
    value = "" if mode is None else str(mode)
    return SEND_MODE_LABELS_RU.get(value, value)


def job_type_to_ru(job_type: object) -> str:
    value = "" if job_type is None else str(job_type)
    return JOB_TYPE_LABELS_RU.get(value, value)


def job_status_to_ru(status: object) -> str:
    value = "" if status is None else str(status)
    return JOB_STATUS_LABELS_RU.get(value, value)


def user_safe_error(message: object) -> str:
    text = "" if message is None else str(message)
    replacements = {
        "GMAIL_APP_PASSWORD is missing. Add it to .env before checking Gmail.": (
            "Gmail не подключен: введите App Password во вкладке Аккаунты и настройки."
        ),
        "GMAIL_APP_PASSWORD is missing. Add it to .env before sending.": (
            "Gmail не подключен: введите App Password во вкладке Аккаунты и настройки."
        ),
        "Gmail app password is missing. Save it in Email settings or configure .env for development.": (
            "Gmail не подключен: введите App Password во вкладке Аккаунты и настройки."
        ),
        "Invalid credentials or Gmail blocked login. Check Gmail address and App Password.": (
            "Invalid credentials: проверьте Gmail address и App Password. Если Gmail заблокировал вход, создайте новый App Password."
        ),
        "Connected. Gmail SMTP login succeeded. No email was sent.": (
            "Connected: Gmail SMTP login successful. Письмо не отправлялось."
        ),
        "Sender email is missing in Settings.": (
            "Не указан email отправителя во вкладке Аккаунты и настройки."
        ),
        "SMTP host is missing in Settings.": "Не указан SMTP-сервер.",
        "SMTP port is missing in Settings.": "Не указан SMTP-порт.",
        "Email is in blacklist": "Получатель в черном списке.",
        "Dry-run only. No SMTP email was sent.": (
            "Тестовый режим: реальное письмо не отправлялось."
        ),
        "Live Gmail send is blocked until the operator explicitly confirms.": (
            "Боевая отправка заблокирована до явного подтверждения оператора."
        ),
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def simple_log_message(row: dict[str, Any]) -> str:
    action = str(row.get("action") or "")
    status = str(row.get("status") or "")
    error = user_safe_error(row.get("error") or "")
    action_labels = {
        "import_contacts": "Импорт получателей",
        "enqueue_generate_messages": "Сообщения поставлены в очередь подготовки",
        "enqueue_ai_generate_drafts": "AI-черновики поставлены в очередь",
        "generate_messages": "Сообщения подготовлены",
        "generate_message": "Сообщение подготовлено",
        "ai_generate_draft": "AI-черновик создан",
        "check_ai_connection": "Проверка AI Assist",
        "save_ai_settings": "AI Assist настройки сохранены",
        "enqueue_send": "Отправка поставлена в очередь",
        "dry_run_send": "Отправка в тестовом режиме завершена",
        "live_send": "Письмо отправлено через Gmail",
        "send_email": "Отправка письма",
        "enqueue_export_report": "Отчет поставлен в очередь",
        "export_report": "Отчет создан",
        "export_report_job": "Отчет создан",
        "check_gmail_connection": "Проверка Gmail",
        "blacklist": "Получатель добавлен в черный список",
        "live_send_cancelled": "Боевая отправка отменена оператором",
    }
    message = action_labels.get(action, action or "Действие")
    if status:
        message += f" - {status_to_ru(status)}"
    if error:
        message += f": {error}"
    return message
