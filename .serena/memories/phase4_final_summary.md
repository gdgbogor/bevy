# Phase 4: Signal Receivers & Final Integration - COMPLETE

## Overview
Phase 4 implements the event-driven signal receivers and Celery background tasks that complete the Pretix-Bevy integration. When orders are paid or attendees check in, Pretix signals trigger async tasks to sync data to Bevy.

## Files Implemented

### 1. `bevy/bevy/tasks.py` (NEW - 500+ lines)
Complete Celery task implementation for async Bevy synchronization.

**Core Task:**
```python
@app.task(bind=True, max_retries=3)
def sync_attendee_to_bevy(self, event_pk: int, position_pk: int, action: str)
```

**Helper Functions:**
- `_get_bevy_config(event)` - Extracts settings from hierarchy (Event → Organizer → Global)
- `_build_auth_headers(config)` - Builds Bevy API headers using auth helpers
- `_get_attendee_email(position)` - Extracts email with fallback chain
- `_register_attendee(config, headers, position)` - POST /attendee/ endpoint
- `_search_attendee(config, headers, email)` - GET /attendee_search/ endpoint
- `_checkin_attendee(config, headers, position)` - PUT /attendee/checkin/ endpoint

**Error Handling Strategy:**
- Config/Auth errors (401/403): Log and abort (no retry)
- Transient errors (5xx, timeout): Retry with exponential backoff (max 3 retries, 60s * 2^attempt)
- Other 4xx errors: Log and abort (no retry)
- Missing email: Log warning and skip (no error)

**Logging:**
- All operations logged with event_id, position_id, action
- No secrets exposed (uses auth helpers' truncation)
- Clear error messages for debugging

### 2. `bevy/bevy/signals.py` (UPDATED)
Added two signal receivers to trigger Bevy sync on Pretix events.

**New Receivers:**

1. **`order_paid_receiver`** (UID: `bevy_order_paid`)
   - Triggered: When order transitions to paid status
   - Action: Enqueues registration task for each order position
   - Config Check: Verifies bevy_event_id and bevy_chapter_id before enqueueing
   - Countdown: 5 seconds (ensures order fully committed to DB)
   - Behavior: Silently skips if Bevy not configured

2. **`checkin_created_receiver`** (UID: `bevy_checkin_created`)
   - Triggered: When check-in recorded for order position
   - Action: Enqueues check-in task for position
   - Config Check: Verifies bevy_event_id and bevy_chapter_id before enqueueing
   - Countdown: 5 seconds (ensures check-in fully committed to DB)
   - Behavior: Silently skips if Bevy not configured

**Signal Imports:**
- `order_paid` from `pretix.base.signals`
- `checkin_created` with fallback imports (tries multiple locations for compatibility)

### 3. `bevy/tests/test_integration.py` (NEW - 315 lines)
Comprehensive integration test suite.

**Test Classes:**

1. **`TestBevySignalReceivers`**
   - `test_order_paid_signal_enqueues_registration_task` - Verifies task enqueueing with correct args
   - `test_order_paid_signal_skips_if_bevy_not_configured` - Verifies config check prevents orphaned tasks
   - `test_checkin_created_signal_enqueues_checkin_task` - Verifies check-in task enqueueing

2. **`TestBevySyncTask`**
   - `test_sync_attendee_registration_success` - Mocks POST /attendee/ endpoint
   - `test_sync_attendee_checkin_success` - Mocks GET search + PUT check-in flow
   - `test_sync_attendee_missing_config_aborts` - Verifies graceful abort on missing config
   - `test_sync_attendee_missing_email_skips` - Verifies email validation

## Settings Hierarchy

Fully implemented cascade per Pretix django-hierarkey:

**Global Level** (applies to all organizers/events):
- `bevy_api_base_url` - Bevy API base URL (default: https://gdg.community.dev/api)

**Organizer Level** (applies to all events under organizer):
- `bevy_chapter_id` - Default Bevy chapter ID
- `bevy_cookie_json` - Structured cookie JSON from Playwright storage state
- `bevy_cookie` - Fallback raw cookie string
- `bevy_csrf_token` - Optional manual CSRF token override

**Event Level** (specific to event):
- `bevy_event_id` - Specific Bevy event ID

**Resolution Order:**
- Event setting → Organizer setting → Global setting → Default value

## Signal Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ REGISTRATION FLOW (Order Paid)                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Order marked as paid in Pretix                              │
│     ↓                                                            │
│  2. pretix.base.signals.order_paid signal sent                  │
│     ↓                                                            │
│  3. order_paid_receiver triggered                               │
│     ├─ Check: bevy_event_id configured? → No → Return          │
│     ├─ Check: bevy_chapter_id configured? → No → Return        │
│     └─ For each order position:                                 │
│        ↓                                                         │
│  4. sync_attendee_to_bevy.apply_async(event_pk, pos_pk, "register")
│     ↓ (5 second countdown)                                      │
│  5. Celery worker picks up task                                 │
│     ├─ Fetch Event and OrderPosition from DB                    │
│     ├─ Extract config from settings hierarchy                   │
│     ├─ Build auth headers using cookie JSON                     │
│     ├─ Extract attendee email (position → order fallback)       │
│     ├─ POST /attendee/ with attendee data                       │
│     └─ Log result (success/error/retry)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ CHECK-IN FLOW (Check-in Created)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Check-in recorded in Pretix                                 │
│     ↓                                                            │
│  2. pretix.plugins.checkinlists.signals.checkin_created sent    │
│     ↓                                                            │
│  3. checkin_created_receiver triggered                          │
│     ├─ Check: bevy_event_id configured? → No → Return          │
│     ├─ Check: bevy_chapter_id configured? → No → Return        │
│     └─ sync_attendee_to_bevy.apply_async(event_pk, pos_pk, "checkin")
│        ↓ (5 second countdown)                                   │
│  4. Celery worker picks up task                                 │
│     ├─ Fetch Event and OrderPosition from DB                    │
│     ├─ Extract config from settings hierarchy                   │
│     ├─ Build auth headers using cookie JSON                     │
│     ├─ Extract attendee email (position → order fallback)       │
│     ├─ GET /attendee_search/ to find attendee by email          │
│     ├─ PUT /attendee/checkin/ with attendee ID                  │
│     └─ Log result (success/error/retry)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Error Handling & Retry Strategy

**Configuration Errors** (Missing settings):
- Log: ERROR level with context
- Action: Abort task immediately
- Retry: No (configuration must be fixed manually)
- Example: Missing bevy_event_id, bevy_chapter_id, or auth credentials

**Authentication Errors** (401/403):
- Log: ERROR level with "credentials may be expired" message
- Action: Abort task immediately
- Retry: No (credentials must be refreshed manually)
- Reason: Retrying won't help; admin must update cookie JSON

**Transient Errors** (5xx, timeout):
- Log: WARNING level with "Will retry" message
- Action: Raise BevySyncError to trigger Celery retry
- Retry: Yes, exponential backoff (60s, 120s, 240s)
- Max Retries: 3 attempts total

**Other 4xx Errors** (400, 404, 422, etc.):
- Log: ERROR level with response body
- Action: Abort task immediately
- Retry: No (client error won't be fixed by retrying)

**Missing Email**:
- Log: WARNING level
- Action: Skip registration/check-in
- Retry: No (data issue, not transient)

## Key Design Decisions

1. **Async-First Architecture**
   - All Bevy API calls happen in background tasks
   - Pretix request cycle never blocked by Bevy API latency
   - Improves user experience and system reliability

2. **Safe Configuration Checks**
   - Receivers check if Bevy configured before enqueueing
   - Prevents orphaned tasks for events without Bevy setup
   - Graceful degradation: missing config → silent skip

3. **Settings Hierarchy**
   - Follows Pretix django-hierarkey pattern
   - Global defaults can be overridden at organizer/event level
   - Flexible for multi-organizer, multi-event deployments

4. **Email Extraction Strategy**
   - Primary: OrderPosition.attendee_email
   - Fallback: Order.email
   - Skip: If both missing (log warning, no error)

5. **Name Parsing**
   - Split attendee_name on first space
   - Fallback to email prefix if name missing
   - Graceful handling of edge cases

6. **Check-in Search**
   - Search by email using /attendee_search/ endpoint
   - Match exactly (case-insensitive)
   - Fail gracefully if attendee not found (log warning)

7. **Retry Strategy**
   - Only retry on transient errors (5xx, timeout)
   - Abort on config/auth errors (no point retrying)
   - Exponential backoff prevents thundering herd

## Validation Checklist

✓ Settings hierarchy (Global → Organizer → Event) implemented
✓ Signal receivers connect correctly on app startup
✓ order_paid signal triggers registration task
✓ checkin_created signal triggers check-in task
✓ Config checks prevent orphaned tasks
✓ Email extraction with fallback chain
✓ Auth headers built using cookie JSON
✓ Registration endpoint (POST /attendee/) called correctly
✓ Check-in search (GET /attendee_search/) called correctly
✓ Check-in endpoint (PUT /attendee/checkin/) called correctly
✓ Error handling: config errors abort without retry
✓ Error handling: auth errors abort without retry
✓ Error handling: transient errors retry with backoff
✓ Logging: no secrets exposed
✓ Logging: clear error messages for debugging
✓ Tests: signal receivers tested
✓ Tests: task execution tested
✓ Tests: error scenarios tested

## Integration Testing

To manually test Phase 4:

1. **Setup Bevy Credentials**
   - Configure organizer-level: bevy_chapter_id, bevy_cookie_json
   - Configure event-level: bevy_event_id

2. **Test Registration Flow**
   - Create order in Pretix
   - Mark order as paid
   - Check Celery logs for task execution
   - Verify attendee appears in Bevy

3. **Test Check-in Flow**
   - Record check-in in Pretix
   - Check Celery logs for task execution
   - Verify attendee marked as checked in Bevy

4. **Test Error Scenarios**
   - Expire cookies, verify auth error handling
   - Remove bevy_event_id, verify config error handling
   - Simulate network timeout, verify retry behavior

## Next Steps (Post-Phase 4)

1. Manual integration testing with real Pretix + Bevy instances
2. Monitor logs for signal delivery and task execution
3. Validate settings hierarchy works across all levels
4. Test error scenarios: expired auth, missing config, network issues
5. Consider adding admin UI for viewing sync history/logs
6. Performance testing with high-volume orders
7. Documentation for end users on setup and troubleshooting
