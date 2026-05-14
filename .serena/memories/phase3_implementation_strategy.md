# Phase 3: Implementation Strategy

## Key Findings

1. **Celery Import**: Use `from pretix.celery_app import app` (standard pretix pattern)
2. **Bevy API Endpoints**:
   - Register: `POST /attendee/?event={event_id}&chapter={chapter_id}` with payload containing `attendees` array
   - Search: `GET /attendee_search/?event={event_id}&chapter={chapter_id}&search={email}`
   - Check-in: `PUT /attendee/checkin/` with payload containing `attendees` array with `id` and `is_checked_in`

3. **Auth Pattern**: Use auth.py helpers to build headers from settings

4. **Error Handling Strategy**:
   - 401/403: Log and abort (auth expired)
   - 429/5xx: Retry with exponential backoff
   - 4xx (other): Log and abort
   - Missing config: Log and abort

## Implementation Order

1. Create `bevy/client.py` - BevyAPIClient class
2. Create `bevy/tasks.py` - Celery task with error handling
3. Update signals.py to enqueue tasks (Phase 4, but prepare structure)

## Code Structure

### client.py
- BevyAPIClient class with timeout support
- Methods: register_attendee, search_attendee, checkin_attendee
- Safe logging (no full headers/tokens)
- Retry logic only for 429/5xx

### tasks.py
- Import from pretix.celery_app
- sync_attendee_to_bevy(event_pk, position_pk, action) task
- Fetch Event/OrderPosition inside task
- Extract settings and build headers
- Handle register/checkin actions with proper error handling
