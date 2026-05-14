# Phase 2: Cookie/Session Generation & Auth Helpers - COMPLETE

## Implementation Summary

Created `bevy/auth.py` with complete authentication helper module.

### Functions Implemented

1. **parse_cookie_json(cookie_json_str: str) -> List[Dict]**
   - Validates JSON syntax
   - Ensures array structure with dict entries
   - Validates each cookie has "name" and "value" keys
   - Confirms "csrftoken" exists in array
   - Raises `BevyCookieError` with clear validation feedback

2. **extract_csrf_token(cookie_json, manual_override=None) -> str**
   - Prefers manual override if provided
   - Falls back to extracting from cookie array
   - Returns normalized token string
   - Raises `BevyCsrfError` if neither source provides token

3. **build_cookie_header(cookie_json) -> str**
   - Filters cookies for `gdg.community.dev` domain match
   - Constructs `name1=value1; name2=value2` format
   - Logs domains found for debugging when filter fails
   - Raises `BevyHeaderError` if no matching domain cookies

4. **build_bevy_headers(base_url, cookie_json, csrf_token) -> Dict[str, str]**
   - Returns dict with required Bevy API headers:
     - `accept: application/json; version=bevy.1.0`
     - `content-type: application/json`
     - `origin: https://gdg.community.dev`
     - `x-requested-with: XMLHttpRequest`
     - `cookie: <built header>`
     - `x-csrftoken: <token>`
   - Validates all inputs before building
   - Raises `BevyHeaderError` on missing base_url or csrf_token

5. **validate_cookie_expiry(cookie_json) -> Tuple[bool, List[str]]**
   - Checks "expires" field in each cookie
   - Returns (is_valid, warnings_list)
   - Marks required cookies (csrftoken, sessionid) with [REQUIRED] tag
   - Near-expiry threshold: 1 day (86400 seconds)
   - Never raises; graceful handling

6. **validate_bevy_auth(base_url, chapter_id, headers, timeout=10.0) -> Tuple[bool, Optional[str]]**
   - Calls `GET /chapter/{chapter_id}/` endpoint
   - Returns (is_valid, error_message)
   - Error message is None if auth successful
   - Never raises exceptions; always safe to call
   - 10-second timeout default
   - Handles Timeout, RequestException, unexpected errors

### Exception Hierarchy

```
BevyAuthError (base)
├── BevyCookieError
├── BevyCsrfError
├── BevyHeaderError
└── BevyAuthValidationError (reserved for future use)
```

### Logging & Security

- `_truncate_secret(value, length=8)` helper function
- Logs show token prefix/suffix only: "abc123...xyz789" or "<32 chars>"
- Never logs full cookie strings or CSRF tokens
- Logs include timestamps (via standard logging)
- Each function includes debug/warning/error logs with context

### Validation Features

- All JSON parsing validates structure before use
- Cookie domain filtering with helpful debug output
- Expiry checking with human-readable remaining time
- Auth endpoint validation returns descriptive errors without exceptions
- Edge case handling: empty strings, missing keys, type mismatches

### Next Steps (Phase 3)

Ready for:
1. Settings forms/views (bevy_cookie_json textarea, chapter_id field)
2. Celery task implementation (uses auth helpers)
3. Signal receivers (enqueue sync tasks)
