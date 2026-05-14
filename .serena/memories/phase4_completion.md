# Phase 4 Completion: Signal Receivers & Final Integration

## Implementation Summary

### 1. Created `bevy/tasks.py` - Celery Background Task
Complete async task for syncing Pretix attendees to Bevy platform.

**Key Functions:**
- `_get_bevy_config(event)`: Extracts settings hierarchy (Event → Organizer → Global)
- `_build_auth_headers(config)`: Builds Bevy API headers using auth helpers
- `_get_attendee_email(position)`: Extracts email from position or order
- `_register_attendee(config, headers, position)`: POST to `/attendee/` endpoint
- `_search_attendee(config, headers, email)`: GET `/attendee_search/` to find attendee
- `_checkin_attendee(config, headers, position)`: PUT to `/attendee/checkin/` endpoint
- `sync_attendee_to_bevy(event_pk, position_pk, action)`: Main Celery task

**Error Handling:**
- Configuration errors: Log and abort (no retry)
- Auth errors (401/403): Log and abort (no retry)
- Transient errors (5xx, timeout): Retry with exponential backoff (max 3 retries)
- Other 4xx errors: Log and abort (no retry)

**Logging:**
- All operations logged with event_id, position_id, action
- No secrets exposed (uses auth helpers' truncation)
- Clear error messages for debugging

### 2. Updated `bevy/signals.py` - Signal Receivers
Added two signal receivers to trigger Bevy sync on Pretix events.

**Receivers:**
1. `order_paid_receiver` (UID: `bevy_order_paid`)
   - Triggered when order transitions to paid
   - Enqueues registration task for each order position
   - Checks if Bevy configured before enqueueing
   - 5-second countdown to ensure order committed

2. `checkin_created_receiver` (UID: `bevy_checkin_created`)
   - Triggered when check-in recorded
   - Enqueues check-in task for position
   - Checks if Bevy configured before enqueueing
   - 5-second countdown to ensure check-in committed

**Signal Imports:**
- `order_paid` from `pretix.base.signals`
- `checkin_created` with fallback imports (tries multiple locations for compatibility)

### 3. Created `tests/test_integration.py` - Integration Tests
Comprehensive test suite covering signal flow and task execution.

**Test Classes:**
1. `TestBevySignalReceivers`
   - `test_order_paid_signal_enqueues_registration_task`: Verifies task enqueueing
   - `test_order_paid_signal_skips_if_bevy_not_configured`: Verifies config check
   - `test_checkin_created_signal_enqueues_checkin_task`: Verifies check-in task

2. `TestBevySyncTask`
   - `test_sync_attendee_registration_success`: Mocks POST to `/attendee/`
   - `test_sync_attendee_checkin_success`: Mocks GET search + PUT check-in
   - `test_sync_attendee_missing_config_aborts`: Verifies graceful abort
   - `test_sync_attendee_missing_email_skips`: Verifies email validation

## Settings Hierarchy Validation

✓ Global Level: `bevy_api_base_url` (defaults to https://gdg.community.dev/api)
✓ Organizer Level: `bevy_chapter_id`, `bevy_cookie_json`, `bevy_cookie`, `bevy_csrf_token`
✓ Event Level: `bevy_event_id`

Cascade: Event → Organizer → Global (as per Pretix django-hierarkey)

## Signal Flow

```
Order Paid Event
  ↓
order_paid_receiver (checks config)
  ↓
For each position:
  sync_attendee_to_bevy.apply_async(event_pk, position_pk, "register")
  ↓
  Task fetches Event/OrderPosition
  ↓
  Extracts config from settings hierarchy
  ↓
  Builds auth headers using cookie JSON
  ↓
  POST /attendee/ with attendee data
  ↓
  Logs result (success/error/retry)

Check-in Created Event
  ↓
checkin_created_receiver (checks config)
  ↓
sync_attendee_to_bevy.apply_async(event_pk, position_pk, "checkin")
  ↓
  Task fetches Event/OrderPosition
  ↓
  Extracts config from settings hierarchy
  ↓
  Builds auth headers using cookie JSON
  ↓
  GET /attendee_search/ to find attendee by email
  ↓
  PUT /attendee/checkin/ with attendee ID
  ↓
  Logs result (success/error/retry)
```

## Key Design Decisions

1. **Async-First**: All Bevy API calls happen in background tasks, not blocking Pretix request cycle
2. **Safe Config Checks**: Receivers check if Bevy configured before enqueueing (no orphaned tasks)
3. **Graceful Degradation**: Missing config/email → log and skip, not error
4. **Retry Strategy**: Only retry on transient errors (5xx, timeout), abort on config/auth errors
5. **Email Fallback**: Position email → Order email → Skip
6. **Name Parsing**: Split attendee_name on space, fallback to email prefix if missing
7. **Exact Email Match**: Check-in searches by email and matches exactly (case-insensitive)

## Files Modified/Created

- ✓ `bevy/bevy/tasks.py` (NEW) - 500+ lines, complete task implementation
- ✓ `bevy/bevy/signals.py` (UPDATED) - Added order_paid and checkin_created receivers
- ✓ `bevy/tests/test_integration.py` (NEW) - 315 lines, comprehensive test suite

## Next Steps (Post-Phase 4)

1. Manual testing with real Pretix event and Bevy instance
2. Monitor logs for signal delivery and task execution
3. Validate settings hierarchy works across Global/Organizer/Event levels
4. Test error scenarios: expired auth, missing config, network timeouts
5. Consider adding admin UI for viewing sync history/logs
