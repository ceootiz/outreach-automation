# Stage 4.7 Operator Throughput Polish

Stage 4.7 makes High Volume Operator Mode faster and more comfortable for real operator sessions while preserving the same safety model: no hidden automation, no autosend, no captcha bypass, no browser farming, and no stealth behavior.

The app may prepare drafts, open public profile URLs, copy text, track local state, and help the operator move quickly. The operator still performs restricted platform actions manually.

## Throughput QA

Stage 4.7 adds a repeatable synthetic QA scenario:

```bash
python scripts/generate_operator_qa_data.py --count 100 --reset
```

The generated dataset is marked as QA/demo and contains only synthetic contacts:

- fake emails under `example.invalid`;
- synthetic channel handles;
- no real tokens;
- no real recipients;
- no live sends.

The dataset mixes:

- Email, Telegram, Instagram, X, TikTok and VK leads;
- high, medium and low priorities;
- AI confidence values;
- enrichment states;
- lead stages;
- follow-up and reply markers.

## Benchmark

Stage 4.7 adds a local benchmark:

```bash
python scripts/operator_throughput_benchmark.py
```

It measures:

- loading 100 leads;
- next lead latency;
- copy message latency;
- mark sent latency;
- filter latency;
- search latency;
- session restore latency.

Target operator-speed thresholds:

- next lead: under 150 ms average;
- filter apply: under 300 ms average;
- copy action: under 100 ms average;
- mark sent: under 250 ms average;
- session restore: under 500 ms average.

No benchmark step sends messages or calls external APIs.

## Keyboard Workflow

High Volume Mode now supports:

- `A` or `Enter`: approve draft;
- `R`: regenerate draft;
- `C` or `Cmd/Ctrl+C`: copy selected draft;
- `O` or `Cmd/Ctrl+O`: open profile/page;
- `S` or `Cmd/Ctrl+S`: mark manually sent;
- `N` or `Space`: next lead;
- `P`: previous lead;
- `F`: schedule follow-up;
- `L`: mark lead warm;
- `1`, `2`, `3`: choose AI variant;
- `Esc`: clear focus safely.

Hotkeys are ignored while the operator is typing in text fields, except `Esc`, so drafts and search input are not accidentally overwritten by session commands.

## Smart Batching

The Outreach Session can order leads by:

- priority;
- new leads;
- AI confidence;
- channel;
- last activity.

This keeps high-value or ready leads near the front without changing any sending behavior.

## Fast Filters

Quick filters help reduce review friction:

- High priority;
- Needs review;
- Ready to send;
- Manual Assist;
- Follow-up due;
- Has reply;
- Low confidence;
- channel filters for Instagram and Telegram;
- search across lead, company, handle, domain and message text.

Filters are persisted with the session so recovery returns the operator to the same working context.

## Session Recovery

The app persists:

- campaign;
- mode;
- active filters;
- lead order;
- current lead;
- review position;
- selected draft variant;
- unsaved draft text;
- session metrics.

If the app closes mid-session, `Restore session` brings the operator back to the current lead without turning any manual action into automation.

## Manual Assist Rules

Manual Assist remains explicit:

- copy prepared text;
- open profile URL when available;
- mark as sent manually;
- track local timeline and metrics.

The app does not log into platforms, click send buttons, bypass rate limits, simulate interaction, or hide automation.

## Operator Feedback

After quick actions the UI gives lightweight feedback:

- copied;
- opened;
- approved;
- skipped;
- marked manually sent;
- follow-up scheduled;
- selected variant.

Dangerous or unsupported actions remain blocked by policy instead of being hidden behind speed workflows.

## Known Limitations

- The benchmark uses local synthetic data and does not represent real network/API latency.
- Social channels without safe official APIs remain Manual Assist only.
- Opening a profile depends on a usable `profile_url` or safe public URL template.
- High-volume review improves operator speed, but it does not relax safe mode, daily limits or human confirmation.
