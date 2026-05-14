"""
Bevy authentication helper functions.

Handles cookie JSON parsing, CSRF token extraction, header building,
and auth validation against Bevy API endpoints.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class BevyAuthError(Exception):
    """Base exception for Bevy authentication errors."""

    pass


class BevyCookieError(BevyAuthError):
    """Raised when cookie JSON is invalid or malformed."""

    pass


class BevyCsrfError(BevyAuthError):
    """Raised when CSRF token cannot be extracted."""

    pass


class BevyHeaderError(BevyAuthError):
    """Raised when required headers cannot be built."""

    pass


class BevyAuthValidationError(BevyAuthError):
    """Raised when auth validation against Bevy API fails."""

    pass


def _truncate_secret(value: str, length: int = 8) -> str:
    """Truncate secret values (tokens, cookies) for safe logging."""
    if not value:
        return "<empty>"
    if len(value) <= length:
        return f"<{len(value)} chars>"
    return f"{value[:length]}...{value[-length:]}"


def parse_cookie_json(cookie_json_str: str) -> List[Dict[str, Any]]:
    """
    Parse JSON string containing cookie array.

    Expected format (Playwright storage state cookies array):
    [
        {"name": "csrftoken", "value": "abc123...", "domain": ".gdg.community.dev", "expires": 1234567890},
        {"name": "sessionid", "value": "xyz789...", "domain": ".gdg.community.dev", "expires": 1234567890},
        ...
    ]

    Args:
        cookie_json_str: JSON string containing cookie array

    Returns:
        Parsed cookie array (list of dicts)

    Raises:
        BevyCookieError: If JSON is invalid or doesn't contain csrftoken
    """
    if not cookie_json_str or not cookie_json_str.strip():
        raise BevyCookieError("Cookie JSON string is empty")

    try:
        cookies = json.loads(cookie_json_str)
    except json.JSONDecodeError as e:
        raise BevyCookieError(f"Invalid JSON in cookie string: {e}")

    if not isinstance(cookies, list):
        raise BevyCookieError(
            f"Cookie JSON must be a list, got {type(cookies).__name__}"
        )

    if not cookies:
        raise BevyCookieError("Cookie JSON array is empty")

    # Validate structure: each cookie should have name and value
    for i, cookie in enumerate(cookies):
        if not isinstance(cookie, dict):
            raise BevyCookieError(f"Cookie at index {i} is not a dict")
        if "name" not in cookie or "value" not in cookie:
            raise BevyCookieError(f"Cookie at index {i} missing 'name' or 'value' keys")

    # Ensure csrftoken exists
    csrf_cookies = [c for c in cookies if c.get("name") == "csrftoken"]
    if not csrf_cookies:
        raise BevyCookieError(
            "No 'csrftoken' found in cookie array. "
            "Ensure credentials were captured from authenticated session."
        )

    logger.debug(
        "Successfully parsed cookie JSON: %d cookies, includes csrftoken", len(cookies)
    )
    return cookies


def extract_csrf_token(
    cookie_json: List[Dict[str, Any]], manual_override: Optional[str] = None
) -> str:
    """
    Extract CSRF token from cookie array.

    Args:
        cookie_json: Parsed cookie array from parse_cookie_json()
        manual_override: If provided, use this instead of extracting from cookies

    Returns:
        CSRF token string

    Raises:
        BevyCsrfError: If CSRF token cannot be extracted and no override provided
    """
    if manual_override:
        if not manual_override.strip():
            raise BevyCsrfError("Manual CSRF token override is empty")
        logger.debug(
            "Using manual CSRF token override: %s", _truncate_secret(manual_override)
        )
        return manual_override.strip()

    # Extract from cookies
    csrf_cookies = [c for c in cookie_json if c.get("name") == "csrftoken"]
    if not csrf_cookies:
        raise BevyCsrfError(
            "No csrftoken found in cookie array and no manual override provided"
        )

    csrf_token = csrf_cookies[0].get("value")
    if not csrf_token or not csrf_token.strip():
        raise BevyCsrfError("csrftoken cookie has empty value")

    logger.debug("Extracted CSRF token: %s", _truncate_secret(csrf_token))
    return csrf_token.strip()


def build_cookie_header(cookie_json: List[Dict[str, Any]]) -> str:
    """
    Build HTTP Cookie header from cookie array, filtering for gdg.community.dev.

    Constructs: "name1=value1; name2=value2; ..."

    Args:
        cookie_json: Parsed cookie array from parse_cookie_json()

    Returns:
        Cookie header string

    Raises:
        BevyHeaderError: If no valid cookies for gdg.community.dev found
    """
    if not cookie_json:
        raise BevyHeaderError("Cookie array is empty")

    # Filter for gdg.community.dev domain
    filtered = [
        c
        for c in cookie_json
        if c.get("domain", "").endswith("gdg.community.dev")
        or c.get("domain") == ".gdg.community.dev"
    ]

    if not filtered:
        # Log all domains for debugging
        domains = set(c.get("domain", "<no domain>") for c in cookie_json)
        logger.warning(
            "No cookies match gdg.community.dev domain. Found domains: %s", domains
        )
        raise BevyHeaderError(
            f"No cookies for gdg.community.dev domain. Found: {domains}"
        )

    # Build cookie string
    cookie_pairs = []
    for cookie in filtered:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value:
            cookie_pairs.append(f"{name}={value}")

    if not cookie_pairs:
        raise BevyHeaderError("No valid name=value pairs in filtered cookies")

    cookie_header = "; ".join(cookie_pairs)
    logger.debug(
        "Built cookie header with %d cookies: %s",
        len(cookie_pairs),
        _truncate_secret(cookie_header),
    )
    return cookie_header


def build_bevy_headers(
    base_url: str, cookie_json: List[Dict[str, Any]], csrf_token: str
) -> Dict[str, str]:
    """
    Build HTTP headers for Bevy API requests.

    Includes: accept, content-type, origin, x-requested-with, cookie, x-csrftoken

    Args:
        base_url: Bevy API base URL (e.g., "https://gdg.community.dev/api")
        cookie_json: Parsed cookie array
        csrf_token: CSRF token string

    Returns:
        Dict of HTTP headers for requests

    Raises:
        BevyHeaderError: If any required header cannot be built
    """
    if not base_url or not base_url.strip():
        raise BevyHeaderError("base_url is empty")

    if not csrf_token or not csrf_token.strip():
        raise BevyHeaderError("csrf_token is empty")

    try:
        cookie_header = build_cookie_header(cookie_json)
    except BevyHeaderError as e:
        raise BevyHeaderError(f"Failed to build cookie header: {e}")

    headers = {
        "accept": "application/json; version=bevy.1.0",
        "content-type": "application/json",
        "origin": "https://gdg.community.dev",
        "x-requested-with": "XMLHttpRequest",
        "cookie": cookie_header,
        "x-csrftoken": csrf_token,
    }

    logger.debug("Built Bevy headers with CSRF token %s", _truncate_secret(csrf_token))
    return headers


def validate_cookie_expiry(cookie_json: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Validate cookie expiry and warn if any are expired or near expiry.

    Args:
        cookie_json: Parsed cookie array

    Returns:
        Tuple of (is_valid, warnings_list)
        - is_valid: True if no expired cookies, False if any expired
        - warnings_list: List of warning messages for expired/near-expiry cookies

    Note:
        Near expiry threshold is 1 day (86400 seconds).
    """
    warnings = []
    now = datetime.utcnow().timestamp()
    near_expiry_threshold = 86400  # 1 day in seconds

    required_cookie_names = {"csrftoken", "sessionid"}

    for cookie in cookie_json:
        name = cookie.get("name")
        expires = cookie.get("expires")

        if expires is None:
            # No expiry means session cookie (expires when browser closes)
            continue

        try:
            expires_timestamp = float(expires)
        except (TypeError, ValueError):
            warnings.append(f"Cookie '{name}': invalid expires value '{expires}'")
            continue

        time_until_expiry = expires_timestamp - now
        is_required = name in required_cookie_names

        if time_until_expiry < 0:
            warning = (
                f"Cookie '{name}' is EXPIRED "
                f"(expired {abs(time_until_expiry):.0f}s ago)"
            )
            warnings.append(warning)
        elif time_until_expiry < near_expiry_threshold:
            warning = (
                f"Cookie '{name}' expires soon "
                f"(in {time_until_expiry:.0f}s, ~{time_until_expiry / 3600:.1f}h)"
            )
            if is_required:
                warning += " [REQUIRED]"
            warnings.append(warning)

    is_valid = not any("EXPIRED" in w for w in warnings)

    if warnings:
        logger.warning(
            "Cookie expiry validation found %d warnings: %s",
            len(warnings),
            "; ".join(warnings),
        )

    return is_valid, warnings


def validate_bevy_auth(
    base_url: str, chapter_id: str, headers: Dict[str, str], timeout: float = 10.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate auth by calling GET /chapter/{chapter_id}/ endpoint.

    Args:
        base_url: Bevy API base URL (e.g., "https://gdg.community.dev/api")
        chapter_id: Bevy chapter ID to validate against
        headers: HTTP headers from build_bevy_headers()
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if auth successful and endpoint returned 200
        - error_message: Error message if auth failed, None if successful

    Note:
        Never raises exceptions; always returns (bool, str|None) for safe graceful handling.
        Logs request details without exposing sensitive headers.
    """
    if not base_url or not chapter_id:
        error = "base_url or chapter_id is empty"
        logger.error("Auth validation failed: %s", error)
        return False, error

    endpoint = f"{base_url.rstrip('/')}/chapter/{chapter_id}/"

    try:
        logger.debug("Validating auth: GET %s [timeout=%s]", endpoint, timeout)

        response = requests.get(endpoint, headers=headers, timeout=timeout)

        if response.status_code == 200:
            logger.info(
                "Auth validation successful: chapter_id=%s, status=%d",
                chapter_id,
                response.status_code,
            )
            return True, None

        # Auth failed
        error_detail = ""
        try:
            error_json = response.json()
            error_detail = error_json.get("detail", "")
        except Exception:
            error_detail = response.text[:200]

        error = (
            f"Auth validation failed with status {response.status_code}: {error_detail}"
        )
        logger.warning(
            "Auth validation failed: chapter_id=%s, status=%d, detail=%s",
            chapter_id,
            response.status_code,
            error_detail,
        )
        return False, error

    except requests.exceptions.Timeout:
        error = f"Auth validation timeout after {timeout}s"
        logger.error("Auth validation timeout: %s", error)
        return False, error

    except requests.exceptions.RequestException as e:
        error = f"Auth validation request failed: {e}"
        logger.error("Auth validation request exception: %s", error)
        return False, error

    except Exception as e:
        error = f"Unexpected error during auth validation: {e}"
        logger.error("Unexpected auth validation error: %s", error)
        return False, error
