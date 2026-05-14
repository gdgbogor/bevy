from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.models import Event
from pretix.control.views.event import EventSettingsFormView, EventSettingsViewMixin

from .forms import EventSettingsForm


class EventSettingsView(EventSettingsViewMixin, EventSettingsFormView):
    """View for managing event-level Bevy settings."""

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
