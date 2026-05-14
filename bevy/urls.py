from django.urls import path

from .views import EventSettingsView, OrganizerSettingsView

app_name = "bevy"
urlpatterns = [
    path(
        "organizer/<organizer>/settings/",
        OrganizerSettingsView.as_view(),
        name="organizer_settings",
    ),
    path(
        "organizer/<organizer>/event/<event>/settings/",
        EventSettingsView.as_view(),
        name="event_settings",
    ),
]
