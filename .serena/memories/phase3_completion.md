# Phase 3: Bevy API Client & Celery Background Tasks - FINAL SUMMARY

## ✅ PHASE 3 COMPLETE

**Execution Date:** 2026-05-14
**Status:** All tasks completed, diagnostics passed, ready for Phase 4

---

## Deliverables

### 1. `bevy/bevy/client.py` (308 lines)

**Purpose:** High-level wrapper for Bevy API endpoints

**Class: BevyAPIClient**

Methods:
- `register_attendee(event_id, chapter_id, attendees, headers)` → POST /attendee/
  - Payload: `{"event": event_id, "attendees": [...]}`
  - Each attendee: first_name, last_name, email, is_checked_in=False, send_event_email=True
  - Returns: Response JSON or error dict

- `search_attendee(event_id, chapter_id, email, headers)` → GET /attendee_search/
  - Query: `?event={event_id}&chapter={chapter_id}&search={email}`
  - Returns: Response with results array

- `checkin_attendee(event_id, chapter_id, attendees, headers)` → PUT /attendee/checkin/
  - Payload: `{"event": event_id, "chapter": chapter_id, "attendees": [...]}`
  - Each attendee: id (int), is_checked_in (bool)
  - Returns: Response JSON or error dict

**Error Handling:**
- Safe logging: truncates secrets, logs status/body only
- Never exposes full auth headers or tokens
- Raises RequestException for network/timeout errors
- Returns error dict for API errors: `{"status": "error", "code": int, "detail": str}`

**Logging:**
- DEBUG: Operation start, parameters
- INFO: Success, found count
- WARNING: API errors with truncated body
- ERROR: Network/timeout errors

---

### 2. `bevy/bevy/tasks.py` (553 lines)

**Purpose:** Celery background task for async Bevy synchronization

**Main Task: `sync_attendee_to_bevy(event_pk, position_pk, action)`**

Decorator: `@app.task(bind=True, max_retries=3)`
Import: `from pretix.celery_app import app`

**Parameters:**
- `event_pk` (int): Pretix Event primary key
- `position_pk` (int): Pretix OrderPosition primary key
- `action` (str): "register" or "checkin"

**Configuration Extraction:**
```
event.settings:
  - bevy_api_base_url (global setting)
  - bevy_event_id (event-level setting)

event.organizer.settings:
  - bevy_chapter_id (organizer-level setting)
  - bevy_cookie_json (organizer-level setting)
  - bevy_csrf_token (organizer-level setting, optional override)
```

**Validation:**
- All required config present
- Cookie JSON valid and contains csrftoken
- CSRF token extractable
- Headers buildable

**Error Handling Strategy:**

| Error Type | Status Code | Behavior | Retry |
|-----------|------------|----------|-------|
| Missing config | N/A | Log error, raise BevyConfigError, abort | ❌ |
| Auth expired | 401, 403 | Log error, return error dict, abort | ❌ |
| Rate limit | 429 | Log warning, raise Exception, retry | ✅ |
| Server error | 5xx | Log warning, raise Exception, retry | ✅ |
| Other 4xx | 4xx | Log error, return error dict, abort | ❌ |
| Unexpected | N/A | Log exception, return error dict, abort | ❌ |

**Register Action (`_handle_register`):**
```
1. Extract attendee data:
   - first_name, last_name from position.attendee_name_parts
   - email from position.attendee_email or position.order.email
   
2. Build attendee dict:
   {
     "first_name": str,
     "last_name": str,
     "email": str,
     "is_checked_in": False,
     "send_event_email": True
   }

3. Call client.register_attendee()

4. Handle response:
   - 200/201: Log success, return success dict
   - 401/403: Log auth error, return error dict
   - 429/5xx: Log warning, raise for retry
   - Other 4xx: Log error, return error dict

5. Return: {"status": "success"|"error", "message": str, "event_id": int, "position_id": int, "email": str}
```

**Check-in Action (`_handle_checkin`):**
```
1. Extract email from position (with fallback to order.email)

2. Search for attendee:
   - Call client.search_attendee(event_id, chapter_id, email, headers)
   - If error: handle per error type
   - If not found: log warning, return not_found error
   - If found: extract attendee.id

3. Check in attendee:
   - Call client.checkin_attendee(event_id, chapter_id, [{"id": id, "is_checked_in": True}], headers)
   - If error: handle per error type
   - If success: log success

4. Return: {"status": "success"|"error", "message": str, "event_id": int, "position_id": int, "email": str, "attendee_id": int}
```

**Exception Hierarchy:**
```
BevySyncError (base)
├── BevyConfigError (missing/invalid config)
└── BevyAuthExpiredError (reserved for future)

Plus auth.py exceptions:
├── BevyCookieError
├── BevyCsrfError
└── BevyHeaderError
```

**Logging:**
- All operations logged with: event_pk, position_pk, action, email, status_code
- Secrets truncated: `abc123...xyz789` or `<32 chars>`
- Response bodies truncated to 200 chars
- Never logs full auth headers or tokens

---

## Integration Points

**Dependencies:**
- `pretix.base.models.Event, OrderPosition` - Fetch data inside task
- `pretix.celery_app.app` - Task decorator and retry logic
- `bevy.auth` - Cookie parsing, CSRF extraction, header building
- `bevy.client.BevyAPIClient` - API calls

**Settings Hierarchy:**
- Global: bevy_api_base_url
- Organizer: bevy_chapter_id, bevy_cookie_json, bevy_csrf_token
- Event: bevy_event_id

---

## Retry Behavior

**Celery Configuration:**
- `max_retries=3`: Up to 3 retry attempts
- Exponential backoff: 2^retry_count seconds (Celery default)
- Jitter: Prevents thundering herd (Celery default)

**Retry Triggers:**
- 429 (rate limit): Raise exception → retry
- 5xx (server error): Raise exception → retry
- All other errors: Return error dict → no retry

---

## Code Quality

**Verification:**
- ✅ No syntax errors (diagnostics passed)
- ✅ All imports correct and available
- ✅ Error handling covers all cases per plan
- ✅ Logging safe (no full secrets)
- ✅ Retry logic for 429/5xx only
- ✅ Config validation before API calls
- ✅ Email extraction with fallback
- ✅ Search before check-in
- ✅ Response parsing with error detection
- ✅ Type hints on all functions
- ✅ Docstrings on all classes/methods

**Lines of Code:**
- client.py: 308 lines
- tasks.py: 553 lines
- Total: 861 lines

---

## Phase 4 Preparation

**Next Steps:**
1. Update `bevy/signals.py` to import `sync_attendee_to_bevy`
2. Add `order_paid` signal receiver
3. Add `checkin_created` signal receiver
4. Enqueue tasks with `apply_async(args=(event_pk, position_pk, action))`

**Expected Signal Flow:**
```
Order Paid Signal
  → order_paid receiver
  → For each position: sync_attendee_to_bevy.apply_async(args=(event_pk, position_pk, "register"))
  → Task enqueued to Celery
  → Background worker executes task
  → Attendee registered to Bevy

Check-in Created Signal
  → checkin_created receiver
  → sync_attendee_to_bevy.apply_async(args=(event_pk, position_pk, "checkin"))
  → Task enqueued to Celery
  → Background worker executes task
  → Attendee searched and checked in to Bevy
```

**Manual Testing (Phase 4):**
1. Configure organizer: bevy_chapter_id, bevy_cookie_json
2. Configure event: bevy_event_id
3. Create paid order → monitor logs for register task
4. Create check-in → monitor logs for checkin task
5. Verify attendees in Bevy dashboard

---

## Summary

Phase 3 successfully implements:
- ✅ BevyAPIClient with three core methods (register, search, checkin)
- ✅ Celery task with robust error handling and retry logic
- ✅ Safe logging (no secrets exposed)
- ✅ Configuration validation
- ✅ Email extraction with fallback
- ✅ Search before check-in workflow
- ✅ Per-plan error handling (retry only for 429/5xx)

Ready for Phase 4: Signal receivers to enqueue tasks on order_paid and checkin_created events.
