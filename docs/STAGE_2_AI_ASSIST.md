# Stage 2 AI Assist

Stage 2 adds a separate `AI Assist` work mode while preserving the existing
manual Gmail outreach flow.

## Modes

Manual mode:

- The operator enters each recipient email, subject, and message.
- Template/manual preparation works as before.
- Sending still requires approval and existing safety guardrails.

AI Assist mode:

- The operator adds recipients and provides a campaign topic.
- Optional recipient data can include name, company, website, social profile,
  and note.
- AI generates a subject and message draft per contact.
- Drafts are saved as `pending_review`.
- AI never approves contacts and never sends email.

## Safety Guarantees

- `send_mode` remains `dry_run` by default.
- AI jobs use `ai_generate_draft`; they do not call SMTP.
- Generated drafts require human review before any send flow can enqueue them.
- `allowed_test_recipient` remains a guardrail only and never rewrites recipients.
- Gmail sender routing still uses the active Gmail profile as `From` and the
  contact row email as `To`.

## Credential Storage

OpenAI API keys are stored through the existing credential storage layer:

- macOS: Keychain where available.
- Windows: Credential Manager where available.
- Fallback: encrypted local storage.

The key is not stored in SQLite, exports, reports, or logs. `.env` with
`OPENAI_API_KEY` is supported only as a development fallback.

## Queue Flow

1. User selects `AI Assist`.
2. User enters `Тема рассылки` and tone.
3. `Сгенерировать черновики` enqueues `ai_generate_draft` jobs.
4. Worker processes jobs sequentially.
5. Each contact is updated with subject/body, AI metadata, and
   `status=pending_review`.
6. The operator edits/approves manually.

## Limitations

- No web browsing or enrichment is performed in Stage 2.0.
- AI uses only data already present in the contact row.
- No automatic sending, auto-replies, tracking, or social-channel automation.
- Large batches are limited by `ai_max_drafts_per_batch` and require explicit
  confirmation from the UI.
