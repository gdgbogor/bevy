from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event, Organizer
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin
from pretix.control.views.organizer import OrganizerSettingsFormView

from .forms import EventSettingsForm, OrganizerSettingsForm


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
