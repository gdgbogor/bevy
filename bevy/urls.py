from django.urls import re_path

from .views import EventSettingsView

app_name = "bevy"
urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/bevy/settings/",
        EventSettingsView.as_view(),
        name="event_settings",
    ),
]
