from django.urls import re_path

from .views import EventSettingsView, OrganizerSettingsView

app_name = "bevy"
urlpatterns = [
    re_path(
        r"^control/organizer/(?P<organizer>[^/]+)/bevy/settings/",
        OrganizerSettingsView.as_view(),
        name="organizer_settings",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/bevy/settings/",
        EventSettingsView.as_view(),
        name="event_settings",
    ),
]
