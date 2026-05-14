"""
Bevy API client wrapper with timeout and error handling support.

Provides a high-level interface to Bevy API endpoints for attendee registration,
search, and check-in operations.
"""

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class BevyAPIClient:
    """
    Client for interacting with Bevy API.

    Handles attendee registration, search, and check-in with safe error handling
    and logging (never logs full auth headers or tokens).
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        """
        Initialize Bevy API client.

        Args:
            base_url: Bevy API base URL (e.g., "https://gdg.community.dev/api")
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _truncate_secret(self, value: str, length: int = 8) -> str:
        """Truncate secret values for safe logging."""
        if not value:
            return "<empty>"
        if len(value) <= length:
            return f"<{len(value)} chars>"
        return f"{value[:length]}...{value[-length:]}"

    def _log_response_error(
        self, status_code: int, response_text: str, context: str = ""
    ) -> None:
        """Log response error safely (truncate body)."""
        truncated_body = response_text[:200] if response_text else "<empty>"
        logger.warning(
            "Bevy API error [%s]: status=%d, body=%s",
            context,
            status_code,
            truncated_body,
        )

    def register_attendee(
        self,
        event_id: str,
        chapter_id: str,
        attendees: List[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Register attendee(s) to a Bevy event.

        Args:
            event_id: Bevy event ID
            chapter_id: Bevy chapter ID
            attendees: List of attendee dicts with keys:
                - first_name (str)
                - last_name (str)
                - email (str)
                - is_checked_in (bool, default False)
                - send_event_email (bool, default True)
            headers: HTTP headers from auth.build_bevy_headers()

        Returns:
            Response JSON from Bevy API

        Raises:
            requests.RequestException: On network/timeout errors
            ValueError: On invalid input
        """
        if not event_id or not chapter_id:
            raise ValueError("event_id and chapter_id are required")

        if not attendees:
            raise ValueError("attendees list cannot be empty")

        url = f"{self.base_url}/attendee/?event={event_id}&chapter={chapter_id}"

        # Ensure attendees have required fields
        for attendee in attendees:
            attendee.setdefault("is_checked_in", False)
            attendee.setdefault("send_event_email", True)

        payload = {"event": event_id, "attendees": attendees}

        logger.debug(
            "Registering %d attendee(s) to event=%s, chapter=%s",
            len(attendees),
            event_id,
            chapter_id,
        )

        try:
            response = self.session.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )

            if response.status_code in (200, 201):
                logger.info(
                    "Successfully registered %d attendee(s): event=%s, status=%d",
                    len(attendees),
                    event_id,
                    response.status_code,
                )
                return response.json()

            # Error response
            self._log_response_error(
                response.status_code,
                response.text,
                f"register_attendee(event={event_id})",
            )
            return {
                "status": "error",
                "code": response.status_code,
                "detail": response.text[:200],
            }

        except requests.exceptions.Timeout:
            logger.error(
                "Timeout registering attendee: event=%s, timeout=%s",
                event_id,
                self.timeout,
            )
            raise

        except requests.exceptions.RequestException as e:
            logger.error(
                "Request error registering attendee: event=%s, error=%s", event_id, e
            )
            raise

    def search_attendee(
        self,
        event_id: str,
        chapter_id: str,
        email: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Search for attendee by email.

        Args:
            event_id: Bevy event ID
            chapter_id: Bevy chapter ID
            email: Email address to search for
            headers: HTTP headers from auth.build_bevy_headers()

        Returns:
            Response JSON from Bevy API (contains results array)

        Raises:
            requests.RequestException: On network/timeout errors
            ValueError: On invalid input
        """
        if not event_id or not chapter_id or not email:
            raise ValueError("event_id, chapter_id, and email are required")

        url = (
            f"{self.base_url}/attendee_search/"
            f"?event={event_id}&chapter={chapter_id}&search={email}"
        )

        logger.debug(
            "Searching attendee: event=%s, chapter=%s, email=%s",
            event_id,
            chapter_id,
            email,
        )

        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)

            if response.status_code == 200:
                result = response.json()
                result_count = len(result.get("results", []))
                logger.info(
                    "Attendee search successful: event=%s, email=%s, found=%d",
                    event_id,
                    email,
                    result_count,
                )
                return result

            # Error response
            self._log_response_error(
                response.status_code,
                response.text,
                f"search_attendee(event={event_id}, email={email})",
            )
            return {
                "status": "error",
                "code": response.status_code,
                "detail": response.text[:200],
            }

        except requests.exceptions.Timeout:
            logger.error(
                "Timeout searching attendee: event=%s, email=%s, timeout=%s",
                event_id,
                email,
                self.timeout,
            )
            raise

        except requests.exceptions.RequestException as e:
            logger.error(
                "Request error searching attendee: event=%s, email=%s, error=%s",
                event_id,
                email,
                e,
            )
            raise

    def checkin_attendee(
        self,
        event_id: str,
        chapter_id: int,
        attendees: List[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Check in attendee(s) to a Bevy event.

        Args:
            event_id: Bevy event ID (str)
            chapter_id: Bevy chapter ID (int)
            attendees: List of attendee dicts with keys:
                - id (int): Bevy attendee ID
                - is_checked_in (bool): True to check in, False to check out
            headers: HTTP headers from auth.build_bevy_headers()

        Returns:
            Response JSON from Bevy API

        Raises:
            requests.RequestException: On network/timeout errors
            ValueError: On invalid input
        """
        if not event_id or chapter_id is None:
            raise ValueError("event_id and chapter_id are required")

        if not attendees:
            raise ValueError("attendees list cannot be empty")

        url = f"{self.base_url}/attendee/checkin/"

        payload = {"event": event_id, "chapter": chapter_id, "attendees": attendees}

        logger.debug(
            "Checking in %d attendee(s): event=%s, chapter=%s",
            len(attendees),
            event_id,
            chapter_id,
        )

        try:
            response = self.session.put(
                url, json=payload, headers=headers, timeout=self.timeout
            )

            if response.status_code == 200:
                logger.info(
                    "Successfully checked in %d attendee(s): event=%s, status=%d",
                    len(attendees),
                    event_id,
                    response.status_code,
                )
                return response.json()

            # Error response
            self._log_response_error(
                response.status_code,
                response.text,
                f"checkin_attendee(event={event_id})",
            )
            return {
                "status": "error",
                "code": response.status_code,
                "detail": response.text[:200],
            }

        except requests.exceptions.Timeout:
            logger.error(
                "Timeout checking in attendee: event=%s, timeout=%s",
                event_id,
                self.timeout,
            )
            raise

        except requests.exceptions.RequestException as e:
            logger.error(
                "Request error checking in attendee: event=%s, error=%s", event_id, e
            )
            raise
