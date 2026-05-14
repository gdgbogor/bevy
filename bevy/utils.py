"""
Utility functions for Bevy integration.
"""

import logging
from typing import Dict, Optional

import requests

from .auth import (
    BevyAuthError,
    build_bevy_headers,
    extract_csrf_token,
    parse_cookie_json,
)

logger = logging.getLogger(__name__)


def test_bevy_connection(
    base_url: str,
    chapter_id: str,
    event_id: Optional[str],
    cookie_json_str: Optional[str],
    cookie_raw: Optional[str],
    csrf_token_override: Optional[str],
) -> Dict[str, any]:
    """
    Test Bevy API connection with provided credentials.

    Args:
        base_url: Bevy API base URL
        chapter_id: Bevy chapter ID
        event_id: Optional Bevy event ID (if testing event-level config)
        cookie_json_str: Cookie JSON string
        cookie_raw: Raw cookie string (fallback)
        csrf_token_override: Manual CSRF token override

    Returns:
        Dict with keys:
            - success (bool): Whether the test succeeded
            - message (str): Human-readable result message
            - details (str): Additional technical details
            - status_code (int): HTTP status code (if request was made)
    """
    result = {
        "success": False,
        "message": "Connection test failed",
        "details": "",
        "status_code": None,
    }

    # Validate required parameters
    if not base_url:
        result["message"] = "Base URL is required"
        result["details"] = "Please configure bevy_api_base_url"
        return result

    if not chapter_id:
        result["message"] = "Chapter ID is required"
        result["details"] = "Please configure bevy_chapter_id"
        return result

    if not (cookie_json_str or cookie_raw or csrf_token_override):
        result["message"] = "Authentication credentials are required"
        result["details"] = (
            "Please provide bevy_cookie_json, bevy_cookie, or bevy_csrf_token"
        )
        return result

    # Build authentication headers
    try:
        if cookie_json_str:
            cookie_json = parse_cookie_json(cookie_json_str)
        else:
            cookie_json = []

        csrf_token = extract_csrf_token(cookie_json, csrf_token_override)
        headers = build_bevy_headers(base_url, cookie_json, csrf_token)

    except BevyAuthError as e:
        result["message"] = "Failed to build authentication headers"
        result["details"] = str(e)
        return result
    except Exception as e:
        result["message"] = "Unexpected error building headers"
        result["details"] = str(e)
        return result

    # Test API endpoint - use chapter endpoint as it's always available
    endpoint = f"{base_url.rstrip('/')}/chapter/{chapter_id}/"

    try:
        logger.info("Testing Bevy API connection: chapter_id=%s", chapter_id)
        response = requests.get(endpoint, headers=headers, timeout=10.0)
        result["status_code"] = response.status_code

        if response.status_code == 200:
            result["success"] = True
            result["message"] = "Connection successful!"

            # Try to extract chapter name from response
            try:
                data = response.json()
                chapter_name = data.get("name", "Unknown")
                result["details"] = f"Successfully connected to chapter: {chapter_name}"
            except Exception:
                result["details"] = "Successfully connected to Bevy API"

            # If event_id provided, also test event endpoint
            if event_id:
                event_endpoint = f"{base_url.rstrip('/')}/event/{event_id}/"
                try:
                    event_response = requests.get(
                        event_endpoint, headers=headers, timeout=10.0
                    )
                    if event_response.status_code == 200:
                        event_data = event_response.json()
                        event_name = event_data.get("name", "Unknown")
                        result["details"] += f"\nEvent verified: {event_name}"
                    else:
                        result["details"] += (
                            f"\nWarning: Event ID {event_id} returned status {event_response.status_code}"
                        )
                except Exception as e:
                    result["details"] += (
                        f"\nWarning: Could not verify event ID: {str(e)}"
                    )

        elif response.status_code == 401:
            result["message"] = "Authentication failed"
            result["details"] = (
                "Invalid or expired credentials. Please update your cookie JSON or CSRF token."
            )

        elif response.status_code == 403:
            result["message"] = "Access forbidden"
            result["details"] = (
                "You don't have permission to access this chapter. Check your credentials and chapter ID."
            )

        elif response.status_code == 404:
            result["message"] = "Chapter not found"
            result["details"] = (
                f"Chapter ID '{chapter_id}' does not exist. Please verify the chapter ID."
            )

        elif response.status_code >= 500:
            result["message"] = "Bevy server error"
            result["details"] = (
                f"Bevy API returned status {response.status_code}. Please try again later."
            )

        else:
            result["message"] = f"Unexpected response (status {response.status_code})"
            result["details"] = (
                response.text[:200] if response.text else "No response body"
            )

    except requests.exceptions.Timeout:
        result["message"] = "Connection timeout"
        result["details"] = (
            f"Could not connect to {base_url} within 10 seconds. Check your network or API URL."
        )

    except requests.exceptions.ConnectionError as e:
        result["message"] = "Connection error"
        result["details"] = f"Could not connect to {base_url}. Error: {str(e)}"

    except requests.exceptions.RequestException as e:
        result["message"] = "Request failed"
        result["details"] = str(e)

    except Exception as e:
        result["message"] = "Unexpected error"
        result["details"] = str(e)
        logger.exception("Unexpected error during Bevy connection test")

    return result
