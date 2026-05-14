# Phase 1 Implementation Complete: Settings Forms/Views/URLs/Navigation

## Files Created

### 1. `bevy/forms.py`
- **OrganizerSettingsForm**: Inherits from `SettingsForm`
  - `bevy_chapter_id`: CharField for default chapter ID
  - `bevy_cookie_json`: Textarea with JSON validation
    - Validates JSON format
    - Validates presence of `csrftoken` cookie
  - `bevy_cookie`: Textarea for raw cookie fallback
  - `bevy_csrf_token`: CharField for manual CSRF override
  - Validation: Requires at least one of (cookie_json, cookie, csrf_token)

- **EventSettingsForm**: Inherits from `SettingsForm`
  - `bevy_event_id`: CharField for event-specific Bevy event ID

### 2. `bevy/views.py`
- **OrganizerSettingsView**: Inherits from `OrganizerDetailViewMixin` + `OrganizerSettingsFormView`
  - Handles organizer-level Bevy settings
  - Redirects to `plugins:bevy:organizer_settings` on success

- **EventSettingsView**: Inherits from `EventSettingsViewMixin` + `EventSettingsFormView`
  - Handles event-level Bevy settings
  - Redirects to `plugins:bevy:event_settings` on success

### 3. `bevy/urls.py`
- Routes:
  - `organizer/<organizer>/settings/` → OrganizerSettingsView (name: `organizer_settings`)
  - `organizer/<organizer>/event/<event>/settings/` → EventSettingsView (name: `event_settings`)

### 4. `bevy/signals.py`
- **register_global_settings**: Registers `bevy_api_base_url` (URLField) as global setting
  - Default: `https://gdg.community.dev/api`
  
- **nav_organizer_settings**: Adds "Bevy Integration" tab to organizer settings page
  - Uses `plugins:bevy:organizer_settings` URL
  
- **nav_event_settings**: Adds "Bevy Integration" tab to event settings page
  - Uses `plugins:bevy:event_settings` URL

### 5. Templates
- `bevy/templates/bevy/organizer_settings.html`: Extends `pretixcontrol/organizers/base.html`
- `bevy/templates/bevy/event_settings.html`: Extends `pretixcontrol/event/settings_base.html`

Both templates use bootstrap3 form layout and follow Pretix conventions.

## Key Features
1. Uses django-hierarkey convention (SettingsForm base class)
2. JSON cookie validation with csrftoken requirement
3. Proper signal integration for navigation
4. Global, organizer, and event-level settings hierarchy
5. No syntax errors or warnings

## Next Steps
Phase 2: Cookie helper functions (parse, derive CSRF, build headers, validate expiry)
