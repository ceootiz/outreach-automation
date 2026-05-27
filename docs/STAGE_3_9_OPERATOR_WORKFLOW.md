# Stage 3.9 Operator Workflow System

Stage 3.9 turns the app from a powerful toolset into a guided operator workflow.
The goal is simple: the operator should understand what to do next, which mode is
safe, and which steps are missing before anything can be launched.

## Campaign Presets

Presets live in `src/presets/` and describe safe defaults:

- B2B Email Outreach
- Influencer Collaboration
- Telegram Outreach
- Partnership Intro
- Affiliate Proposal

Each preset stores:

- recommended channel;
- recommended execution mode;
- AI tone and AI usage;
- suggested workflow;
- recommended limits;
- follow-up strategy;
- warnings;
- AI prompt hints.

Presets never enable live send automatically. They set the app to safe
configuration such as dry-run or Manual Assist.

## New Campaign Wizard

The campaign wizard guides the operator through:

1. Choose preset
2. Choose channel
3. Choose execution mode
4. Configure AI
5. Import recipients
6. Validate campaign
7. Launch draft generation

The wizard creates a campaign and applies safe defaults. It does not send,
approve, or enqueue live sends.

## Campaign Validation

Before launch, the app builds a checklist:

- active sender or channel account configured;
- AI configured when the preset expects AI;
- recipients imported;
- safe mode enabled;
- daily limit set;
- Telegram token present when needed;
- Manual Assist recommended for restricted channels;
- follow-up configured.

Checklist rows use `ok`, `warning`, or `error` and are intentionally
operator-facing rather than developer-facing.

## Health Score

Campaign Health Score is a simple 0-100 signal:

- `Healthy`
- `Needs attention`
- `Risky`

It is based on missing recipients, missing sender/channel setup, AI setup,
safe-mode configuration, daily limit, follow-up setup and channel execution
risk.

## Smart Warnings

Smart warnings appear before send/manual execution paths where relevant:

- bulk live send without dry-run;
- restricted channel not using Manual Assist;
- Telegram recipients missing `chat_id`;
- low AI confidence or AI warnings;
- live mode with safe mode disabled;
- no recipients.

Warnings are advisory unless an existing guardrail blocks the action. Existing
safe-mode, recipient routing, confirmation and rate-limit checks remain the
source of truth for blocking unsafe live actions.

## Quick Start

Quick Start creates safe preconfigured campaigns:

- Quick Email Outreach
- Quick Telegram Campaign
- Quick AI Draft Generation

All Quick Start flows keep `send_mode=dry_run` and do not autosend.

## Operator Dashboard

The Campaigns screen now includes an operator dashboard with:

- active campaigns;
- drafts pending review;
- replies waiting;
- follow-up reminders;
- risk alerts;
- AI warnings.

This is not an analytics-heavy CRM view. It is a compact “what needs attention”
surface.

## Campaign Archive And Duplicate

Operators can archive or duplicate campaigns.

Duplicated contacts are reset to `new` and require review. No send jobs are
created by archive or duplicate actions.

## Safety Philosophy

Stage 3.9 does not add unsafe automation:

- no hidden autosend;
- no auto-approve;
- no AI auto-reply;
- no unsupported social automation;
- Human confirmation remains mandatory;
- Email and Telegram keep their existing safe-mode and routing guardrails;
- Manual Assist remains explicit for restricted social channels.
