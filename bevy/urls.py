from django.urls import re_path

from .views import (
    EventSettingsView,
    OrganizerSettingsView,
    test_connection_event,
    test_connection_organizer,
)

app_name = "bevy"
urlpatterns = [
    re_path(
        r"^control/organizer/(?P<organizer>[^/]+)/bevy/settings/$",
        OrganizerSettingsView.as_view(),
        name="organizer_settings",
    ),
    re_path(
        r"^control/organizer/(?P<organizer>[^/]+)/bevy/test-connection/$",
        test_connection_organizer,
        name="test_connection_organizer",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/bevy/settings/$",
        EventSettingsView.as_view(),
        name="event_settings",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/bevy/test-connection/$",
        test_connection_event,
        name="test_connection_event",
    ),
]
