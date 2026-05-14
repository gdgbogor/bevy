# Bevy API — Complete Endpoint & Functionality Reference

This document describes every endpoint in the `bevy-api` project, how it interacts with the upstream **Bevy (GDG Community Dev)** platform API at `https://gdg.community.dev/api`, and the authentication flow that underpins all operations.

---

## Architecture Overview

```
┌──────────────┐    HTTP     ┌──────────────────┐   HTTP (proxied)   ┌──────────────────────────┐
│  Client App  │ ──────────► │  bevy-api (Fast   │ ─────────────────► │  Bevy Platform API       │
│  (Frontend)  │             │  API on :8000)    │                    │  gdg.community.dev/api   │
└──────────────┘             └──────────────────┘                    └──────────────────────────┘
                                    │
                                    │  Reads tokens from
                                    ▼
                             ┌──────────────────┐
                             │ auth_state.json   │
                             │ (Playwright       │
                             │  storage state)   │
                             └──────────────────┘
                                    ▲
                                    │  Written by /auth/login
                                    │  via Chrome Remote Debug
                                    │
                             ┌──────────────────┐
                             │  Chrome Browser   │
                             │  (port 9222 CDP)  │
                             └──────────────────┘
```

**Flow Summary:**
1. A human logs into `gdg.community.dev` in a Chrome instance running with `--remote-debugging-port=9222`.
2. The `/auth/login` endpoint connects to that Chrome instance via Playwright CDP, navigates to the GDG site, waits for the dashboard, then saves the browser's full cookie/storage state to `auth_state.json`.
3. All subsequent API calls (`/events`, `/attendees`, `/chapters`) read `auth_state.json` to extract the CSRF token and cookie string, then proxy requests to the Bevy API with those credentials injected as headers.

---

## Common Authentication Mechanism

**File:** `app/core/utils.py` → `get_tokens_from_state()`

Every endpoint (except `/auth/login` and `/`) calls `get_tokens_from_state()` which:
1. Opens `auth_state.json` (Playwright storage state file).
2. Iterates over all cookies, building a cookie string (`key=value; key=value; ...`).
3. Extracts the `csrftoken` cookie specifically.
4. Returns `(cookie_string, csrf_token)`.

If `auth_state.json` doesn't exist, returns `(None, None)`, and endpoints raise a **401 Unauthorized** with `"Auth state not found. Run /auth/login."`.

**Common Headers** (from `config.py`):
```
accept: application/json; version=bevy.1.0
content-type: application/json
origin: https://gdg.community.dev
x-requested-with: XMLHttpRequest
```
Plus per-request:
```
cookie: <full cookie string from auth_state.json>
x-csrftoken: <csrftoken value>
```

---

## Endpoints

### 1. Health Check

| Property | Value |
|----------|-------|
| **Route** | `GET /` |
| **File** | `app/main.py` |
| **Auth Required** | No |
| **Bevy API Call** | None |

**Behavior:**
Returns a simple JSON welcome message and a link to the docs.

**Response:**
```json
{
  "message": "Welcome to Bevy GDG API",
  "docs": "/docs"
}
```

---

### 2. Authentication — Login

| Property | Value |
|----------|-------|
| **Route** | `POST /auth/login` |
| **File** | `app/api/endpoints/auth.py` |
| **Auth Required** | No (creates auth) |
| **Bevy API Call** | None (uses browser automation) |
| **Response Model** | `AuthResponse` |

**How It Works:**
1. Connects to a running Chrome instance via **Chrome DevTools Protocol (CDP)** on `localhost:{REMOTE_DEBUGGING_PORT}` (default `9222`) using Playwright's `chromium.connect_over_cdp()`.
2. Uses the **first existing browser context** (or creates a new one if none exist).
3. Opens a new page and navigates to `https://gdg.community.dev/`.
4. Waits up to **60 seconds** for the URL to match `**/dashboard/**` — indicating the user is logged in.
5. Saves the full browser context storage state (cookies, localStorage, sessionStorage) to `auth_state.json`.
6. Reads back the tokens using `get_tokens_from_state()`.
7. Returns the captured CSRF token and cookie string.

**Prerequisites:**
- Chrome must be running with `google-chrome --remote-debugging-port=9222`.
- The user must be logged into `gdg.community.dev` in that Chrome instance.

**Error Responses:**
| Code | Condition |
|------|-----------|
| `503` | Cannot connect to Chrome on the configured port |
| `408` | Dashboard URL not detected within 60s (user not logged in) |
| `500` | Any other unexpected error |

**Response Schema (`AuthResponse`):**
```json
{
  "message": "Success! Tokens captured.",
  "csrf_token": "abc123...",
  "cookie_string": "csrftoken=abc123; sessionid=xyz789; ..."
}
```

---

### 3. Events — List Events

| Property | Value |
|----------|-------|
| **Route** | `GET /events/` |
| **File** | `app/api/endpoints/events.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `GET /api/event/?chapter={chapter_id}&order_by=-start_date&page=1&page_size=25` |

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `chapter_id` | `str` | `681` (GDG Bogor) | The Bevy chapter ID to fetch events for |

**How It Works:**
1. Reads auth tokens from `auth_state.json`.
2. Constructs URL: `{BASE_URL}/event/?chapter={chapter_id}&order_by=-start_date&page=1&page_size=25`
3. Sends `GET` request to the Bevy API with auth headers.
4. If Bevy returns `200`, returns the JSON response directly (paginated event list).
5. Otherwise returns `{"status": "error", "code": <status>, "detail": <response_text>}`.

**Note:** Pagination is hardcoded to `page=1&page_size=25` — only the first page of 25 events is returned. The response is ordered by `start_date` descending (newest first).

**Bevy Response Structure (typical):**
```json
{
  "count": 42,
  "next": "...",
  "previous": null,
  "results": [
    {
      "id": 120062,
      "title": "DevFest Bogor 2025",
      "start_date": "2025-12-01T09:00:00+07:00",
      "end_date": "2025-12-01T17:00:00+07:00",
      "chapter": 681,
      ...
    }
  ]
}
```

---

### 4. Events — Get Event Detail

| Property | Value |
|----------|-------|
| **Route** | `GET /events/{event_id}` |
| **File** | `app/api/endpoints/events.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `GET /api/event/{event_id}/?chapter={chapter_id}` |

**Path Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `event_id` | `str` | The numeric Bevy event ID |

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `chapter_id` | `str` | `681` | The Bevy chapter ID |

**How It Works:**
1. Reads auth tokens.
2. Constructs URL: `{BASE_URL}/event/{event_id}/?chapter={chapter_id}`
3. Proxies the `GET` request to Bevy.
4. Returns the raw Bevy JSON (full event object with all metadata) on `200`, or an error object otherwise.

**Use Case:** Retrieve detailed info about a specific event — description, venue, schedule, ticket types, speakers, etc.

---

### 5. Attendees — List/Search Attendees

| Property | Value |
|----------|-------|
| **Route** | `GET /attendees/` |
| **File** | `app/api/endpoints/attendees.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `GET /api/attendee_search/?event={event_id}&chapter={chapter_id}&page={page}&page_size={page_size}&search={search}` |

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `event_id` | `str` | *required* | The Bevy event ID to search attendees for |
| `chapter_id` | `str` | `681` | The chapter ID |
| `page` | `int` | `1` | Page number for pagination |
| `page_size` | `int` | `25` | Number of results per page |
| `search` | `str` | `""` | Search query (name/email filter) |

**How It Works:**
1. Reads auth tokens.
2. Constructs URL with all query params forwarded to Bevy's `attendee_search` endpoint.
3. Returns the Bevy JSON on `200`, or raw response text on error.

**Key Difference:** This uses Bevy's `/attendee_search/` endpoint (not `/attendee/`), which supports full-text search across attendee records.

**Bevy Response Structure (typical):**
```json
{
  "count": 150,
  "next": "...",
  "results": [
    {
      "id": 12345,
      "first_name": "John",
      "last_name": "Doe",
      "email": "john@example.com",
      "is_checked_in": false,
      ...
    }
  ]
}
```

---

### 6. Attendees — Register Attendee

| Property | Value |
|----------|-------|
| **Route** | `POST /attendees/register` |
| **File** | `app/api/endpoints/attendees.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `POST /api/attendee/?event={event_id}&chapter={chapter_id}` |

**Request Body (`RegisterRequest`):**
```json
{
  "event_id": "120062",
  "chapter_id": "681",
  "first_name": "Dery",
  "last_name": "Sudrajat",
  "email": "dery.sudrajat17@gmail.com"
}
```

**How It Works:**
1. Reads auth tokens.
2. Constructs URL: `{BASE_URL}/attendee/?event={event_id}&chapter={chapter_id}`
3. Builds payload with the attendee wrapped in an `attendees` array:
   ```json
   {
     "event": "120062",
     "attendees": [{
       "first_name": "Dery",
       "last_name": "Sudrajat",
       "email": "dery.sudrajat17@gmail.com",
       "is_checked_in": false,
       "send_event_email": true
     }]
   }
   ```
4. Sends `POST` to Bevy API.
5. Returns Bevy JSON on `200` or `201`, otherwise raw text.

**Key Behaviors:**
- `is_checked_in` is always set to `false` (attendee is registered but not checked in).
- `send_event_email` is always `true` (the attendee receives an event confirmation email from Bevy).
- Only **one attendee** is registered per request (despite the array structure).

---

### 7. Attendees — Check In / Un-check In

| Property | Value |
|----------|-------|
| **Route** | `PUT /attendees/checkin` |
| **File** | `app/api/endpoints/attendees.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `PUT /api/attendee/checkin/` |

**Request Body (`CheckInRequest`):**
```json
{
  "event_id": "120062",
  "chapter_id": 681,
  "attendees": [
    { "id": 12345, "is_checked_in": true },
    { "id": 12346, "is_checked_in": false }
  ]
}
```

**How It Works:**
1. Reads auth tokens.
2. Constructs payload:
   ```json
   {
     "event": "120062",
     "chapter": 681,
     "attendees": [
       { "id": 12345, "is_checked_in": true },
       { "id": 12346, "is_checked_in": false }
     ]
   }
   ```
3. Sends `PUT` to `{BASE_URL}/attendee/checkin/`.
4. Returns Bevy JSON on `200`, otherwise raw text.

**Key Behaviors:**
- Supports **batch check-in**: multiple attendees can be checked in/out in a single request.
- `is_checked_in: true` checks the attendee in; `false` reverses it.
- `chapter_id` is an `int` here (unlike other endpoints where it's a `str`) — see schemas.

**Note on `CheckInAttendee` schema:**
- `id`: The Bevy attendee ID (integer), obtained from the list/search attendees response.
- `is_checked_in`: Boolean toggle for check-in status.

---

### 8. Chapters — Get Chapter Detail

| Property | Value |
|----------|-------|
| **Route** | `GET /chapters/{chapter_id}` |
| **File** | `app/api/endpoints/chapters.py` |
| **Auth Required** | Yes |
| **Bevy API Endpoint** | `GET /api/chapter/{chapter_id}/` |

**Path Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `chapter_id` | `str` | `681` (GDG Bogor) | The Bevy chapter ID |

**How It Works:**
1. Reads auth tokens.
2. Proxies to `{BASE_URL}/chapter/{chapter_id}/`.
3. Returns the raw Bevy chapter metadata JSON on `200`, otherwise raw text.

**Use Case:** Retrieve chapter metadata — name, location, description, member count, social links, logo, etc.

---

## Pydantic Schemas Summary

| Schema | File | Fields | Used By |
|--------|------|--------|---------|
| `RegisterRequest` | `schemas.py` | `event_id`, `chapter_id`, `first_name`, `last_name`, `email` | `POST /attendees/register` |
| `CheckInAttendee` | `schemas.py` | `id` (int), `is_checked_in` (bool) | Nested in `CheckInRequest` |
| `CheckInRequest` | `schemas.py` | `event_id` (str), `chapter_id` (int), `attendees` (List[CheckInAttendee]) | `PUT /attendees/checkin` |
| `AuthResponse` | `schemas.py` | `message`, `csrf_token` (optional), `cookie_string` (optional) | `POST /auth/login` |

---

## Bevy API Endpoints Mapped

| Local Route | Method | Bevy API Endpoint |
|-------------|--------|-------------------|
| `/auth/login` | POST | *(browser automation, no API call)* |
| `/events/` | GET | `GET /api/event/?chapter=...&order_by=-start_date&page=1&page_size=25` |
| `/events/{event_id}` | GET | `GET /api/event/{event_id}/?chapter=...` |
| `/attendees/` | GET | `GET /api/attendee_search/?event=...&chapter=...&page=...&page_size=...&search=...` |
| `/attendees/register` | POST | `POST /api/attendee/?event=...&chapter=...` |
| `/attendees/checkin` | PUT | `PUT /api/attendee/checkin/` |
| `/chapters/{chapter_id}` | GET | `GET /api/chapter/{chapter_id}/` |

---

## Important Notes & Quirks

1. **Session Expiry:** The auth tokens in `auth_state.json` will expire when the Bevy session expires. There's no automatic refresh — you must re-run `POST /auth/login` with a logged-in Chrome session.

2. **Hardcoded Pagination on Events:** `GET /events/` always fetches `page=1&page_size=25`. There are no query params exposed to paginate further.

3. **Inconsistent `chapter_id` Types:** In `RegisterRequest` it's a `str`, in `CheckInRequest` it's an `int`. The Bevy API likely accepts both, but this inconsistency could cause issues.

4. **No Error Response Models:** Non-200 responses from Bevy are returned as raw text or a generic error dict, not validated through Pydantic models.

5. **Synchronous HTTP:** The app uses `requests` (synchronous) inside a FastAPI app. For high concurrency, this blocks the event loop. Consider switching to `httpx` async client for production use.

6. **Single Attendee Registration:** Despite Bevy's API supporting batch registration (the `attendees` array), this wrapper only registers one attendee at a time.

7. **Services Directory:** `app/services/` exists but is empty — reserved for future refactoring of business logic out of endpoint handlers.
