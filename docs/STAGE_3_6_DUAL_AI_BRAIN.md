# Stage 3.6 Dual AI Brain

Stage 3.6 adds a two-step AI draft pipeline while keeping the existing manual
and simple AI flows intact.

## Research Brain

Research Brain receives only the contact row and the campaign topic:

- email and email domain;
- name;
- company;
- website URL;
- social/profile URL;
- channel;
- note;
- campaign topic.

There is no web browsing in Stage 3.6. Domain heuristics are allowed only as
low-confidence hints. The brief must include `source_basis` and warnings when
there is not enough information.

Research Brain returns a structured recipient brief:

- recipient type;
- likely context;
- positioning angle;
- message hooks;
- do-not-claim list;
- personalization strength;
- confidence;
- warnings;
- source basis.

## Writer Brain

Writer Brain receives:

- campaign topic;
- tone;
- channel context;
- contact row data;
- recipient brief;
- safety constraints.

For Email it returns subject and body. For social channels it returns body only.
Writer Brain must not add facts that are not present in the brief and must
respect the `do_not_claim` list.

## Key Storage

Settings now expose separate credential controls:

- Research Brain provider/model/API key;
- Writer Brain provider/model/API key.

The same OpenAI key can be saved for both, or two different keys can be used.
Keys are saved through `credential_store` and are not stored in SQLite, exports,
reports or logs.

Development fallbacks:

- `OPENAI_RESEARCH_API_KEY`;
- `OPENAI_WRITER_API_KEY`;
- `OPENAI_API_KEY` as legacy fallback.

## Queue Flow

The new queue job is `ai_dual_brain_generate`:

1. transition contact to `generating`;
2. run Research Brain;
3. run Writer Brain with the structured brief;
4. save draft fields and research metadata;
5. set contact status to `pending_review`;
6. record timeline, send log and AI metrics.

Standalone future-ready jobs also exist:

- `ai_research_contact`;
- `ai_write_from_brief`.

## Safety Guarantees

- AI does not send messages.
- AI does not approve contacts.
- AI does not change sender or recipient.
- All drafts stay `pending_review`.
- Social channels do not get an email subject.
- Missing data becomes a warning, not a fabricated fact.
- Research Brain cannot claim web browsing or site/profile inspection.
- Writer Brain cannot claim research beyond the brief.

## Future Enrichment Slot

Stage 3.6 adds an enrichment package with a disabled default implementation:

```text
src/enrichment/
  base.py
  disabled_enricher.py
```

This keeps the architecture ready for a future explicit web-enrichment stage
without allowing hidden browsing in the current release.

## Tests

`tests/test_stage_3_6_dual_ai_brain.py` covers:

- separate Research/Writer key storage;
- one-key-for-both support;
- no API keys in SQLite;
- anti-hallucination prompt rules;
- low-data research warnings;
- dual-brain pending-review drafts;
- no autosend and no autoapprove;
- social channel drafts without subject;
- old simple AI mode compatibility;
- visible masked UI controls.
