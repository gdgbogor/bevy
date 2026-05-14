"""
Celery background tasks for Bevy integration.

Handles asynchronous synchronization of Pretix attendees to Bevy platform.
"""

import json
import logging
from typing import Optional

import requests
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event, OrderPosition
from pretix.celery_app import app

from .auth import (
    BevyAuthError,
    build_bevy_headers,
    extract_csrf_token,
    parse_cookie_json,
)

logger = logging.getLogger(__name__)


class BevySyncError(Exception):
    """Base exception for Bevy sync errors."""

    pass


def _get_bevy_config(event: Event) -> dict:
    """
    Extract Bevy configuration from event settings hierarchy.

    Settings cascade: Event → Organizer → Global

    Args:
        event: Pretix Event instance

    Returns:
        Dict with keys: base_url, chapter_id, event_id, cookie_json, csrf_token

    Raises:
        BevySyncError: If required settings are missing
    """
    # Get base URL (Global level)
    base_url = (
        event.settings.get("bevy_api_base_url") or "https://gdg.community.dev/api"
    )

    # Get chapter ID (Organizer level, fallback to Event level)
    chapter_id = event.organizer.settings.get("bevy_chapter_id") or event.settings.get(
        "bevy_chapter_id"
    )

    # Get event ID (Event level)
    event_id = event.settings.get("bevy_event_id")

    # Get auth credentials (Organizer level)
    cookie_json_str = event.organizer.settings.get("bevy_cookie_json")
    cookie_raw = event.organizer.settings.get("bevy_cookie")
    csrf_token_override = event.organizer.settings.get("bevy_csrf_token")

    # Validate required settings
    if not chapter_id:
        raise BevySyncError(
            f"Bevy chapter_id not configured for event {event.pk}. "
            "Set at organizer or event level."
        )

    if not event_id:
        raise BevySyncError(
            f"Bevy event_id not configured for event {event.pk}. Set at event level."
        )

    if not (cookie_json_str or cookie_raw or csrf_token_override):
        raise BevySyncError(
            f"Bevy auth not configured for organizer {event.organizer.pk}. "
            "Provide bevy_cookie_json, bevy_cookie, or bevy_csrf_token."
        )

    return {
        "base_url": base_url,
        "chapter_id": chapter_id,
        "event_id": event_id,
        "cookie_json_str": cookie_json_str,
        "cookie_raw": cookie_raw,
        "csrf_token_override": csrf_token_override,
    }


def _build_auth_headers(config: dict) -> dict:
    """
    Build Bevy API headers from configuration.

    Args:
        config: Dict from _get_bevy_config()

    Returns:
        Dict of HTTP headers for Bevy API requests

    Raises:
        BevySyncError: If headers cannot be built
    """
    try:
        # Parse cookie JSON if provided
        if config["cookie_json_str"]:
            cookie_json = parse_cookie_json(config["cookie_json_str"])
        else:
            # Fallback: create minimal cookie array from raw cookie string
            # This is a fallback path; ideally cookie_json_str is always provided
            logger.warning(
                "Using fallback raw cookie string instead of structured JSON. "
                "Prefer bevy_cookie_json for better validation."
            )
            cookie_json = []

        # Extract CSRF token
        csrf_token = extract_csrf_token(cookie_json, config["csrf_token_override"])

        # Build headers
        headers = build_bevy_headers(config["base_url"], cookie_json, csrf_token)
        return headers

    except BevyAuthError as e:
        raise BevySyncError(f"Failed to build auth headers: {e}")


def _get_attendee_email(position: OrderPosition) -> Optional[str]:
    """
    Extract email from order position or fallback to order email.

    Args:
        position: OrderPosition instance

    Returns:
        Email string or None if not found
    """
    # Try position attendee email first
    if position.attendee_email:
        return position.attendee_email

    # Fallback to order email
    if position.order and position.order.email:
        return position.order.email

    return None


def _register_attendee(config: dict, headers: dict, position: OrderPosition) -> bool:
    """
    Register attendee in Bevy.

    Args:
        config: Dict from _get_bevy_config()
        headers: Dict from _build_auth_headers()
        position: OrderPosition instance

    Returns:
        True if successful, False otherwise

    Raises:
        BevySyncError: On configuration or network errors
    """
    email = _get_attendee_email(position)
    if not email:
        logger.warning(
            "Cannot register position %d: no email found. Skipping registration.",
            position.pk,
        )
        return False

    # Extract name from attendee name or order
    attendee_name = position.attendee_name or ""
    parts = attendee_name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    if not first_name:
        first_name = position.order.email.split("@")[0] if position.order else "Guest"

    endpoint = (
        f"{config['base_url'].rstrip('/')}/attendee/"
        f"?event={config['event_id']}&chapter={config['chapter_id']}"
    )

    payload = {
        "event": config["event_id"],
        "attendees": [
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "is_checked_in": False,
                "send_event_email": True,
            }
        ],
    }

    try:
        logger.debug(
            "Registering attendee: event=%s, position=%d, email=%s",
            config["event_id"],
            position.pk,
            email,
        )

        response = requests.post(endpoint, json=payload, headers=headers, timeout=10.0)

        if response.status_code in (200, 201):
            logger.info(
                "Successfully registered attendee: position=%d, email=%s, status=%d",
                position.pk,
                email,
                response.status_code,
            )
            return True

        # Handle errors
        if response.status_code in (401, 403):
            logger.error(
                "Auth failed during registration: position=%d, status=%d. "
                "Bevy credentials may be expired.",
                position.pk,
                response.status_code,
            )
            raise BevySyncError(
                f"Auth failed (status {response.status_code}). Credentials may be expired."
            )

        if response.status_code >= 500:
            logger.warning(
                "Bevy server error during registration: position=%d, status=%d. "
                "Will retry.",
                position.pk,
                response.status_code,
            )
            raise BevySyncError(f"Bevy server error (status {response.status_code})")

        # Other 4xx errors: log and don't retry
        logger.error(
            "Registration failed: position=%d, status=%d, response=%s",
            position.pk,
            response.status_code,
            response.text[:200],
        )
        return False

    except requests.exceptions.Timeout:
        logger.error("Registration timeout: position=%d", position.pk)
        raise BevySyncError("Request timeout")

    except requests.exceptions.RequestException as e:
        logger.error(
            "Registration request failed: position=%d, error=%s", position.pk, e
        )
        raise BevySyncError(f"Request failed: {e}")


def _search_attendee(config: dict, headers: dict, email: str) -> Optional[dict]:
    """
    Search for attendee in Bevy by email.

    Args:
        config: Dict from _get_bevy_config()
        headers: Dict from _build_auth_headers()
        email: Email address to search for

    Returns:
        Attendee dict with 'id' key if found, None otherwise
    """
    endpoint = (
        f"{config['base_url'].rstrip('/')}/attendee_search/"
        f"?event={config['event_id']}&chapter={config['chapter_id']}&search={email}"
    )

    try:
        logger.debug(
            "Searching for attendee: event=%s, email=%s",
            config["event_id"],
            email,
        )

        response = requests.get(endpoint, headers=headers, timeout=10.0)

        if response.status_code != 200:
            logger.warning(
                "Attendee search failed: email=%s, status=%d",
                email,
                response.status_code,
            )
            return None

        data = response.json()
        results = data.get("results", [])

        # Find exact email match
        for attendee in results:
            if attendee.get("email", "").lower() == email.lower():
                logger.debug(
                    "Found attendee: email=%s, bevy_id=%s",
                    email,
                    attendee.get("id"),
                )
                return attendee

        logger.debug("No exact email match found: email=%s", email)
        return None

    except requests.exceptions.RequestException as e:
        logger.error("Attendee search request failed: email=%s, error=%s", email, e)
        return None


def _checkin_attendee(config: dict, headers: dict, position: OrderPosition) -> bool:
    """
    Check in attendee in Bevy.

    Args:
        config: Dict from _get_bevy_config()
        headers: Dict from _build_auth_headers()
        position: OrderPosition instance

    Returns:
        True if successful, False otherwise

    Raises:
        BevySyncError: On configuration or network errors
    """
    email = _get_attendee_email(position)
    if not email:
        logger.warning(
            "Cannot check in position %d: no email found. Skipping check-in.",
            position.pk,
        )
        return False

    # Search for attendee by email
    attendee = _search_attendee(config, headers, email)
    if not attendee:
        logger.warning(
            "Attendee not found in Bevy for check-in: position=%d, email=%s. "
            "May need to register first.",
            position.pk,
            email,
        )
        return False

    attendee_id = attendee.get("id")
    if not attendee_id:
        logger.error(
            "Attendee found but missing ID: position=%d, email=%s",
            position.pk,
            email,
        )
        return False

    endpoint = f"{config['base_url'].rstrip('/')}/attendee/checkin/"

    payload = {
        "event": config["event_id"],
        "chapter": int(config["chapter_id"]),
        "attendees": [{"id": attendee_id, "is_checked_in": True}],
    }

    try:
        logger.debug(
            "Checking in attendee: event=%s, position=%d, bevy_id=%s",
            config["event_id"],
            position.pk,
            attendee_id,
        )

        response = requests.put(endpoint, json=payload, headers=headers, timeout=10.0)

        if response.status_code == 200:
            logger.info(
                "Successfully checked in attendee: position=%d, bevy_id=%s",
                position.pk,
                attendee_id,
            )
            return True

        # Handle errors
        if response.status_code in (401, 403):
            logger.error(
                "Auth failed during check-in: position=%d, status=%d. "
                "Bevy credentials may be expired.",
                position.pk,
                response.status_code,
            )
            raise BevySyncError(
                f"Auth failed (status {response.status_code}). Credentials may be expired."
            )

        if response.status_code >= 500:
            logger.warning(
                "Bevy server error during check-in: position=%d, status=%d. "
                "Will retry.",
                position.pk,
                response.status_code,
            )
            raise BevySyncError(f"Bevy server error (status {response.status_code})")

        # Other 4xx errors: log and don't retry
        logger.error(
            "Check-in failed: position=%d, status=%d, response=%s",
            position.pk,
            response.status_code,
            response.text[:200],
        )
        return False

    except requests.exceptions.Timeout:
        logger.error("Check-in timeout: position=%d", position.pk)
        raise BevySyncError("Request timeout")

    except requests.exceptions.RequestException as e:
        logger.error("Check-in request failed: position=%d, error=%s", position.pk, e)
        raise BevySyncError(f"Request failed: {e}")


@app.task(bind=True, max_retries=3)
def sync_attendee_to_bevy(self, event_pk: int, position_pk: int, action: str):
    """
    Sync Pretix attendee to Bevy platform.

    Handles both registration and check-in actions. Retries on transient errors
    (5xx, timeouts) but aborts on configuration or auth errors.

    Args:
        event_pk: Pretix Event primary key
        position_pk: Pretix OrderPosition primary key
        action: "register" or "checkin"

    Raises:
        BevySyncError: On configuration or permanent errors (no retry)
    """
    try:
        # Fetch models
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

        # Validate action
        if action not in ("register", "checkin"):
            logger.error("Invalid action: %s. Must be 'register' or 'checkin'.", action)
            return

        logger.info(
            "Starting Bevy sync: event=%d, position=%d, action=%s",
            event_pk,
            position_pk,
            action,
        )

        # Get configuration
        try:
            config = _get_bevy_config(event)
        except BevySyncError as e:
            logger.error("Configuration error: %s. Aborting without retry.", e)
            return

        # Build auth headers
        try:
            headers = _build_auth_headers(config)
        except BevySyncError as e:
            logger.error("Auth header error: %s. Aborting without retry.", e)
            return

        # Execute action
        if action == "register":
            success = _register_attendee(config, headers, position)
        else:  # checkin
            success = _checkin_attendee(config, headers, position)

        if success:
            logger.info(
                "Bevy sync completed successfully: event=%d, position=%d, action=%s",
                event_pk,
                position_pk,
                action,
            )
        else:
            logger.warning(
                "Bevy sync completed with warnings: event=%d, position=%d, action=%s",
                event_pk,
                position_pk,
                action,
            )

    except BevySyncError as e:
        # Transient error: retry with exponential backoff
        logger.warning(
            "Transient error during Bevy sync (attempt %d/%d): %s. Retrying...",
            self.request.retries + 1,
            self.max_retries,
            e,
        )
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))

    except Exception as e:
        # Unexpected error: log and abort
        logger.error(
            "Unexpected error during Bevy sync: event=%d, position=%d, error=%s",
            event_pk,
            position_pk,
            e,
            exc_info=True,
        )
