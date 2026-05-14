import json

from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from pretix.base.models import Event, Organizer
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.control.views.organizer import OrganizerSettingsFormView

from .forms import EventSettingsForm, OrganizerSettingsForm
from .utils import test_bevy_connection


class OrganizerSettingsView(OrganizerSettingsFormView):
    """Bevy settings stored on organizer level."""

    form_class = OrganizerSettingsForm
    template_name = "bevy/organizer_settings.html"

    def get_success_url(self):
        return reverse(
            "plugins:bevy:organizer_settings",
            kwargs={"organizer": self.request.organizer.slug},
        )


class EventSettingsView(EventSettingsViewMixin, EventSettingsFormView):
    """Bevy settings stored on event level."""

    model = Event
    permission = "can_change_settings"
    form_class = EventSettingsForm
    template_name = "bevy/event_settings.html"

    def get_success_url(self):
        return reverse(
            "plugins:bevy:event_settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


@require_http_methods(["POST"])
def test_connection_organizer(request, organizer):
    """AJAX endpoint to test Bevy API connection for organizer settings."""
    try:
        organizer_obj = Organizer.objects.get(slug=organizer)
    except Organizer.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Organizer not found"}, status=404
        )

    # Check permissions
    if not request.user.has_organizer_permission(
        organizer_obj, "can_change_organizer_settings", request
    ):
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    # Get configuration from POST data (unsaved form values)
    base_url = (
        request.POST.get("bevy_api_base_url", "").strip()
        or "https://gdg.community.dev/api"
    )
    chapter_id = request.POST.get("bevy_chapter_id", "").strip()
    cookie_json_str = request.POST.get("bevy_cookie_json", "").strip()
    cookie_raw = request.POST.get("bevy_cookie", "").strip()
    csrf_token_override = request.POST.get("bevy_csrf_token", "").strip()

    # Run connection test
    result = test_bevy_connection(
        base_url=base_url,
        chapter_id=chapter_id,
        event_id=None,  # No event ID at organizer level
        cookie_json_str=cookie_json_str,
        cookie_raw=cookie_raw,
        csrf_token_override=csrf_token_override,
    )

    return JsonResponse(result)


@require_http_methods(["POST"])
def test_connection_event(request, organizer, event):
    """AJAX endpoint to test Bevy API connection for event settings."""
    try:
        event_obj = Event.objects.get(slug=event, organizer__slug=organizer)
    except Event.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Event not found"}, status=404
        )

    # Check permissions
    if not request.user.has_event_permission(
        event_obj.organizer, event_obj, "can_change_event_settings", request
    ):
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    # Get configuration from POST data and settings hierarchy
    base_url = (
        request.POST.get("bevy_api_base_url", "").strip()
        or event_obj.settings.get("bevy_api_base_url")
        or "https://gdg.community.dev/api"
    )

    # Chapter ID from organizer settings
    chapter_id = (
        event_obj.organizer.settings.get("bevy_chapter_id")
        or event_obj.settings.get("bevy_chapter_id")
        or ""
    )

    # Event ID from POST data (current form value)
    event_id = request.POST.get("bevy_event_id", "").strip()

    # Auth from organizer settings
    cookie_json_str = event_obj.organizer.settings.get("bevy_cookie_json") or ""
    cookie_raw = event_obj.organizer.settings.get("bevy_cookie") or ""
    csrf_token_override = event_obj.organizer.settings.get("bevy_csrf_token") or ""

    # Run connection test
    result = test_bevy_connection(
        base_url=base_url,
        chapter_id=chapter_id,
        event_id=event_id,
        cookie_json_str=cookie_json_str,
        cookie_raw=cookie_raw,
        csrf_token_override=csrf_token_override,
    )

    return JsonResponse(result)
