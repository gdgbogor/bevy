from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import order_paid, register_global_settings
from pretix.control.signals import nav_event_settings, nav_organizer

from .forms import EventSettingsForm, OrganizerSettingsForm
from .tasks import sync_attendee_to_bevy

# Import checkin_created signal - try multiple locations for compatibility
try:
    from pretix.plugins.checkinlists.signals import checkin_created
except ImportError:
    try:
        from pretix.plugins.ticketoutput_pdf.signals import checkin_created
    except ImportError:
        from django.dispatch import Signal

        checkin_created = Signal()


@receiver(register_global_settings, dispatch_uid="bevy_register_global_settings")
def register_global_settings_receiver(sender, **kwargs):
    """Register Bevy API URL in global settings."""
    return OrderedDict(
        [
            (
                "bevy_api_base_url",
                forms.URLField(
                    label=_("Bevy API Base URL"),
                    help_text=_(
                        "Base URL for Bevy API. Default: https://gdg.community.dev/api"
                    ),
                    required=False,
                    initial="https://gdg.community.dev/api",
                ),
            ),
        ]
    )


@receiver(nav_organizer, dispatch_uid="bevy_nav_organizer_settings")
def nav_organizer_settings_receiver(sender, organizer, request, **kwargs):
    """Add Bevy tab to organizer detail page navigation."""
    url = resolve(request.path_info)
    return [
        {
            "label": _("Bevy"),
            "url": reverse(
                "plugins:bevy:organizer_settings",
                kwargs={"organizer": organizer.slug},
            ),
            "active": url.namespace == "plugins:bevy"
            and url.url_name == "organizer_settings",
        }
    ]


@receiver(nav_event_settings, dispatch_uid="bevy_nav_event_settings")
def nav_event_settings_receiver(sender, request, **kwargs):
    """Add Bevy tab to event settings page."""
    url = resolve(request.path_info)
    return [
        {
            "label": _("Bevy"),
            "url": reverse(
                "plugins:bevy:event_settings",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            ),
            "active": url.namespace == "plugins:bevy"
            and url.url_name == "event_settings",
        }
    ]


@receiver(order_paid, dispatch_uid="bevy_order_paid")
def order_paid_receiver(sender, order, **kwargs):
    event = sender

    if not event.settings.get("bevy_event_id"):
        return

    if not event.organizer.settings.get("bevy_chapter_id"):
        return

    for position in order.positions.all():
        sync_attendee_to_bevy.apply_async(
            args=(event.pk, position.pk, "register"),
            countdown=5,
        )


@receiver(checkin_created, dispatch_uid="bevy_checkin_created")
def checkin_created_receiver(sender, checkin, **kwargs):
    event = sender
    position = checkin.position

    if not event.settings.get("bevy_event_id"):
        return

    if not event.organizer.settings.get("bevy_chapter_id"):
        return

    sync_attendee_to_bevy.apply_async(
        args=(event.pk, position.pk, "checkin"),
        countdown=5,
    )
