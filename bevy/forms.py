import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from pretix.base.forms import SettingsForm


class OrganizerSettingsForm(SettingsForm):
    """Settings form for organizer-level Bevy configuration."""

    bevy_chapter_id = forms.CharField(
        label=_("Bevy Chapter ID"),
        help_text=_("Default Bevy chapter ID for all events under this organizer."),
        required=False,
        max_length=255,
    )

    bevy_cookie_json = forms.CharField(
        label=_("Bevy Cookie JSON"),
        help_text=_(
            "Structured cookie JSON from Playwright storage state or generated helper. "
            "Must contain at least 'csrftoken' cookie."
        ),
        widget=forms.Textarea(attrs={"rows": 6}),
        required=False,
    )

    bevy_cookie = forms.CharField(
        label=_("Bevy Cookie (Manual Override)"),
        help_text=_(
            "Fallback raw cookie string for emergency use. Prefer bevy_cookie_json."
        ),
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )

    bevy_csrf_token = forms.CharField(
        label=_("Bevy CSRF Token (Manual Override)"),
        help_text=_(
            "Optional manual override. If empty, derived from csrftoken cookie in JSON."
        ),
        required=False,
        max_length=255,
    )

    def clean_bevy_cookie_json(self):
        """Validate bevy_cookie_json is valid JSON and contains csrftoken."""
        value = self.cleaned_data.get("bevy_cookie_json", "").strip()
        if not value:
            return value

        try:
            cookies = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValidationError(
                _("Invalid JSON format: {error}").format(error=str(e))
            )

        if not isinstance(cookies, list):
            raise ValidationError(_("Cookie JSON must be a list of cookie objects."))

        # Validate presence of csrftoken
        csrf_found = any(cookie.get("name") == "csrftoken" for cookie in cookies)
        if not csrf_found:
            raise ValidationError(
                _("Cookie JSON must contain at least 'csrftoken' cookie.")
            )

        return value

    def clean(self):
        """Validate that at least one auth method is provided."""
        cleaned_data = super().clean()
        cookie_json = cleaned_data.get("bevy_cookie_json", "").strip()
        cookie_raw = cleaned_data.get("bevy_cookie", "").strip()
        csrf_token = cleaned_data.get("bevy_csrf_token", "").strip()

        has_json = bool(cookie_json)
        has_raw = bool(cookie_raw)
        has_csrf = bool(csrf_token)

        if not (has_json or has_raw or has_csrf):
            raise ValidationError(
                _(
                    "Provide at least one of: bevy_cookie_json, bevy_cookie, or bevy_csrf_token."
                )
            )

        return cleaned_data


class EventSettingsForm(SettingsForm):
    """Settings form for event-level Bevy configuration."""

    bevy_event_id = forms.CharField(
        label=_("Bevy Event ID"),
        help_text=_("Specific Bevy event ID for this Pretix event."),
        required=False,
        max_length=255,
    )
