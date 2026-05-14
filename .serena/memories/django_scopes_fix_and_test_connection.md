# Django Scopes Fix and Test Connection Feature

## Date: 2026-05-14

## Problem Identified

The Bevy sync task was failing with the following error:
```
django_scopes.exceptions.ScopeError: A scope on dimension(s) organizer needs to be active for this query.
```

This occurred in the `sync_attendee_to_bevy` Celery task when trying to query `Event.objects.get(pk=event_pk)` without an active scope context.

## Root Cause

Pretix uses `django-scopes` to ensure queries are properly scoped to prevent data leakage between organizers. Celery tasks run outside the request context, so they don't have an active scope by default. When the task tried to query the Event model (which is scoped to the organizer dimension), it failed because no scope was active.

## Solution 1: Django Scopes Fix

### File: `bevy/tasks.py`

**Changes:**
1. Added import: `from django_scopes import scopes_disabled`
2. Wrapped model queries in `scopes_disabled()` context manager in the `sync_attendee_to_bevy` task

**Code:**
```python
@app.task(bind=True, max_retries=3)
def sync_attendee_to_bevy(self, event_pk: int, position_pk: int, action: str):
    try:
        # Fetch models - disable scopes since Celery tasks run outside request context
        with scopes_disabled():
            try:
                event = Event.objects.get(pk=event_pk)
            except Event.DoesNotExist:
                logger.error("Event not found: pk=%d", event_pk)
                return

            try:
                position = OrderPosition.objects.get(pk=position_pk)
            except OrderPosition.DoesNotExist:
                logger.error("OrderPosition not found: pk=%d", position_pk)
                return
        
        # Rest of the task logic continues...
```

**Why this works:**
- `scopes_disabled()` temporarily disables scope checking for queries within its context
- This is the recommended approach for background tasks according to django-scopes documentation
- The queries are safe because we're fetching specific objects by primary key (not filtering across tenants)

## Solution 2: Test Connection Feature

Added a "Test Connection" button to both organizer and event settings pages that allows users to validate their Bevy API configuration before saving.

### New File: `bevy/utils.py`

Created utility module with `test_bevy_connection()` function that:
- Validates required configuration parameters
- Builds authentication headers
- Tests the Bevy API by calling the chapter endpoint
- Optionally tests the event endpoint if event_id is provided
- Returns detailed success/failure information with helpful error messages

**Key features:**
- Tests chapter endpoint: `GET /chapter/{chapter_id}/`
- Optionally tests event endpoint: `GET /event/{event_id}/`
- Extracts chapter/event names from API responses
- Provides specific error messages for different failure scenarios:
  - 401: Authentication failed (expired credentials)
  - 403: Access forbidden (permission issue)
  - 404: Chapter/Event not found
  - 5xx: Server error
  - Timeout: Connection timeout
  - Connection errors: Network issues

### Updated File: `bevy/views.py`

Added two AJAX endpoints:

1. **`test_connection_organizer(request, organizer)`**
   - Tests organizer-level configuration
   - Uses form values from POST data (unsaved)
   - Tests chapter endpoint only

2. **`test_connection_event(request, organizer, event)`**
   - Tests event-level configuration
   - Combines event form values with organizer settings
   - Tests both chapter and event endpoints
   - Uses settings hierarchy (Event → Organizer → Global)

Both endpoints:
- Check user permissions
- Return JSON responses
- Handle errors gracefully

### Updated File: `bevy/urls.py`

Added URL patterns:
- `/control/organizer/{organizer}/bevy/test-connection/` → `test_connection_organizer`
- `/control/event/{organizer}/{event}/bevy/test-connection/` → `test_connection_event`

### Updated Templates

**`bevy/templates/bevy/organizer_settings.html`:**
- Added "Test Connection" button with icon
- Added loading spinner
- Added result display area (success/error alerts)
- Added JavaScript to handle AJAX request and display results

**`bevy/templates/bevy/event_settings.html`:**
- Same features as organizer template
- Added help text explaining it uses organizer-level auth
- Tests both chapter and event endpoints

### User Experience

1. User fills in configuration fields (doesn't need to save)
2. Clicks "Test Connection" button
3. Spinner appears while testing
4. Result appears in colored alert box:
   - **Green (success):** Shows chapter name and event name (if applicable)
   - **Red (failure):** Shows specific error message and details
5. User can fix issues and test again before saving

### Benefits

- **Immediate feedback:** Users know if their configuration works before saving
- **Better error messages:** Specific guidance on what's wrong (expired auth, wrong ID, etc.)
- **Saves time:** No need to trigger actual sync tasks to test configuration
- **Confidence:** Users can verify everything works before going live
- **Debugging:** Shows HTTP status codes and API responses for troubleshooting

## Testing Recommendations

1. **Test the django-scopes fix:**
   - Create an order and mark it as paid
   - Check Celery logs - should no longer see ScopeError
   - Verify attendee is registered in Bevy

2. **Test the connection feature:**
   - Go to organizer settings
   - Fill in valid credentials and click "Test Connection"
   - Should see green success message with chapter name
   - Try invalid credentials - should see red error message
   - Go to event settings
   - Fill in event ID and click "Test Connection"
   - Should see success with both chapter and event names

## Files Modified

1. `bevy/tasks.py` - Added django-scopes fix
2. `bevy/utils.py` - NEW - Test connection utility
3. `bevy/views.py` - Added AJAX endpoints
4. `bevy/urls.py` - Added URL patterns
5. `bevy/templates/bevy/organizer_settings.html` - Added test button and JavaScript
6. `bevy/templates/bevy/event_settings.html` - Added test button and JavaScript

## Summary

This update fixes the critical django-scopes error that was preventing the Bevy sync from working, and adds a valuable "Test Connection" feature that improves the user experience when configuring the integration.
