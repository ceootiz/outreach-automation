# Stage 4.6 High Volume Operator Mode

Stage 4.6 adds a fast operator workflow for high-volume review and manual-assisted execution.

This is not stealth automation. The app does not solve captchas, bypass limits, simulate hidden browser activity, farm accounts, evade bans, or send messages in the background.

## Modes

- Precision Mode: slower, high-touch review with deeper personalization.
- High Volume Mode: keyboard-first conveyor review for shorter drafts and faster manual execution.

Both modes keep human confirmation and manual control.

## Outreach Session

The new `Outreach Session` screen guides the operator through:

1. lead summary
2. AI brief/draft review
3. quick approve/regenerate
4. copy prepared text
5. open profile/page
6. operator sends manually where required
7. mark sent
8. next lead

The system can help prepare and organize work, but the operator performs restricted social-platform actions manually.

## Hotkeys

- `A`: approve draft
- `R`: regenerate draft
- `C`: copy message
- `O`: open profile/page
- `S`: mark manually sent
- `N`: next lead
- `P`: previous lead
- `F`: follow-up
- `L`: set lead status
- `1`: short variant
- `2`: friendly variant
- `3`: direct variant

## Priority Engine

Leads are ranked as:

- High Priority
- Medium Priority
- Low Priority

Signals include AI confidence, enrichment quality, research strength, channel clarity, lead stage, company/name availability, warnings, spam risk, and draft readiness.

Priority labels help the operator decide order. They do not trigger autosend.

## Manual Assist

For Instagram, X, TikTok and VK, the app uses Manual Assist:

- copy message
- open profile link
- mark sent manually
- update timeline

No hidden login, no DM automation, no browser hacking, no fake interaction simulation.

## Rate Control

High Volume Mode still respects:

- safe mode
- daily limits
- per-channel execution policies
- manual confirmation
- cooldown warnings

If a limit is reached, the session pauses or warns. It never attempts to bypass platform limits.

## Session Analytics

The local session tracks:

- reviewed leads
- copied messages
- manually sent count
- replies received
- AI acceptance rate
- follow-up conversion

These metrics are operator workflow signals, not a trigger for automatic sending.

## AI Feedback

Operators can mark AI output as:

- useful
- generic
- inaccurate
- too aggressive
- weak personalization

Feedback is stored locally for future tuning. It does not update prompts or send anything automatically.

## Session Recovery

The app persists:

- current session
- current lead
- filters
- review position
- selected draft variant

If the app closes, the operator can restore the session and continue.

## Safety Guarantees

Stage 4.6 preserves:

- no autosend
- no hidden automation
- no captcha solving
- no stealth behavior
- no recipient rewriting
- no secret leakage
- human review before execution

## Known Limitations

- High Volume Mode does not add new official APIs.
- Social-channel sending remains Manual Assist unless a channel has a safe official integration.
- AI variants are local fast variants unless full AI regeneration is queued and configured.
- Performance was smoke-tested, but very large real campaigns still need live operator QA.
