# Phase 4 Plan: Signal Receivers & Final Integration

## Tasks
1. Create `bevy/tasks.py` with Celery task `sync_attendee_to_bevy`
   - Accept: event_pk, position_pk, action (register/checkin)
   - Fetch Event and OrderPosition 
   - Extract settings hierarchy: Event → Organizer → Global
   - Call Bevy API endpoints
   - Error handling with logs

2. Update `bevy/signals.py` with:
   - Import: `order_paid` from `pretix.base.signals`
   - Import: `checkin_created` from pretix checkin models
   - Create `order_paid` receiver (UID: `bevy_order_paid`)
   - Create `checkin_created` receiver (UID: `bevy_checkin_created`)
   - Both check Bevy config before enqueueing tasks

3. Validation & Testing:
   - Settings hierarchy working (Global → Org → Event)
   - Signal receivers connect on app startup
   - Integration test: one paid order → one check-in

## Key Points
- Use Bevy auth helpers from `bevy/auth.py`
- Log safely (no secrets, truncated values)
- Handle missing config gracefully (no retry)
- Handle auth errors (401/403) carefully
- Handle transient errors (429, 5xx) with Celery backoff
- Never expose full cookies/tokens in logs
