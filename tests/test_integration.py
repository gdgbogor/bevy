"""
Integration tests for Bevy signal receivers and task execution.

Tests the complete flow: order paid → signal → task → Bevy API call.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from pretix.base.models import Event, Order, OrderPosition, Organizer
from pretix.testutils.fixtures import event, order_position, organizer

from bevy.tasks import sync_attendee_to_bevy


class TestBevySignalReceivers(TestCase):
    """Test Bevy signal receivers and task enqueueing."""

    def setUp(self):
        """Set up test fixtures."""
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.event = Event.objects.create(
            organizer=self.organizer,
            name="Test Event",
            slug="test-event",
            date_from="2025-12-01",
        )

        # Configure Bevy settings
        self.organizer.settings.set("bevy_chapter_id", "681")
        self.organizer.settings.set(
            "bevy_cookie_json",
            json.dumps(
                [
                    {
                        "name": "csrftoken",
                        "value": "test_csrf_token_123",
                        "domain": ".gdg.community.dev",
                    },
                    {
                        "name": "sessionid",
                        "value": "test_session_id_456",
                        "domain": ".gdg.community.dev",
                    },
                ]
            ),
        )
        self.event.settings.set("bevy_event_id", "120062")
        self.event.settings.set("bevy_api_base_url", "https://gdg.community.dev/api")

    def test_order_paid_signal_enqueues_registration_task(self):
        """Test that order_paid signal enqueues registration tasks."""
        # Create an order with positions
        order = Order.objects.create(
            event=self.event,
            email="test@example.com",
            status=Order.STATUS_PENDING,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
            attendee_name="John Doe",
        )

        # Mock the task
        with patch("bevy.signals.sync_attendee_to_bevy.apply_async") as mock_task:
            # Trigger order_paid signal
            from bevy.signals import order_paid_receiver

            order_paid_receiver(sender=self.event, order=order)

            # Verify task was enqueued
            mock_task.assert_called_once()
            call_args = mock_task.call_args
            assert call_args[1]["args"] == (self.event.pk, position.pk, "register")
            assert call_args[1]["countdown"] == 5

    def test_order_paid_signal_skips_if_bevy_not_configured(self):
        """Test that order_paid signal is skipped if Bevy not configured."""
        # Create event without Bevy config
        event_no_bevy = Event.objects.create(
            organizer=self.organizer,
            name="No Bevy Event",
            slug="no-bevy-event",
            date_from="2025-12-01",
        )

        order = Order.objects.create(
            event=event_no_bevy,
            email="test@example.com",
            status=Order.STATUS_PENDING,
        )

        OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
        )

        # Mock the task
        with patch("bevy.signals.sync_attendee_to_bevy.apply_async") as mock_task:
            # Trigger order_paid signal
            from bevy.signals import order_paid_receiver

            order_paid_receiver(sender=event_no_bevy, order=order)

            # Verify task was NOT enqueued
            mock_task.assert_not_called()

    def test_checkin_created_signal_enqueues_checkin_task(self):
        """Test that checkin_created signal enqueues check-in tasks."""
        # Create an order with position
        order = Order.objects.create(
            event=self.event,
            email="test@example.com",
            status=Order.STATUS_PAID,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
            attendee_name="Jane Doe",
        )

        # Mock checkin object
        mock_checkin = MagicMock()
        mock_checkin.position = position

        # Mock the task
        with patch("bevy.signals.sync_attendee_to_bevy.apply_async") as mock_task:
            # Trigger checkin_created signal
            from bevy.signals import checkin_created_receiver

            checkin_created_receiver(sender=self.event, checkin=mock_checkin)

            # Verify task was enqueued
            mock_task.assert_called_once()
            call_args = mock_task.call_args
            assert call_args[1]["args"] == (self.event.pk, position.pk, "checkin")
            assert call_args[1]["countdown"] == 5


class TestBevySyncTask(TestCase):
    """Test the sync_attendee_to_bevy Celery task."""

    def setUp(self):
        """Set up test fixtures."""
        self.organizer = Organizer.objects.create(name="Test Org", slug="test-org")
        self.event = Event.objects.create(
            organizer=self.organizer,
            name="Test Event",
            slug="test-event",
            date_from="2025-12-01",
        )

        # Configure Bevy settings
        self.organizer.settings.set("bevy_chapter_id", "681")
        self.organizer.settings.set(
            "bevy_cookie_json",
            json.dumps(
                [
                    {
                        "name": "csrftoken",
                        "value": "test_csrf_token_123",
                        "domain": ".gdg.community.dev",
                    },
                    {
                        "name": "sessionid",
                        "value": "test_session_id_456",
                        "domain": ".gdg.community.dev",
                    },
                ]
            ),
        )
        self.event.settings.set("bevy_event_id", "120062")
        self.event.settings.set("bevy_api_base_url", "https://gdg.community.dev/api")

    def test_sync_attendee_registration_success(self):
        """Test successful attendee registration."""
        order = Order.objects.create(
            event=self.event,
            email="test@example.com",
            status=Order.STATUS_PAID,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
            attendee_name="John Doe",
        )

        # Mock requests.post for registration
        with patch("bevy.tasks.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_post.return_value = mock_response

            # Execute task
            sync_attendee_to_bevy(self.event.pk, position.pk, "register")

            # Verify API was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "attendee" in call_args[0][0]
            assert (
                call_args[1]["json"]["attendees"][0]["email"] == "attendee@example.com"
            )

    def test_sync_attendee_checkin_success(self):
        """Test successful attendee check-in."""
        order = Order.objects.create(
            event=self.event,
            email="test@example.com",
            status=Order.STATUS_PAID,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
            attendee_name="Jane Doe",
        )

        # Mock requests.get for search and requests.put for check-in
        with (
            patch("bevy.tasks.requests.get") as mock_get,
            patch("bevy.tasks.requests.put") as mock_put,
        ):
            # Mock search response
            search_response = MagicMock()
            search_response.status_code = 200
            search_response.json.return_value = {
                "results": [
                    {
                        "id": 12345,
                        "email": "attendee@example.com",
                        "first_name": "Jane",
                        "last_name": "Doe",
                    }
                ]
            }
            mock_get.return_value = search_response

            # Mock check-in response
            checkin_response = MagicMock()
            checkin_response.status_code = 200
            mock_put.return_value = checkin_response

            # Execute task
            sync_attendee_to_bevy(self.event.pk, position.pk, "checkin")

            # Verify search was called
            mock_get.assert_called_once()
            assert "attendee_search" in mock_get.call_args[0][0]

            # Verify check-in was called
            mock_put.assert_called_once()
            assert "checkin" in mock_put.call_args[0][0]
            assert mock_put.call_args[1]["json"]["attendees"][0]["id"] == 12345

    def test_sync_attendee_missing_config_aborts(self):
        """Test that missing config causes task to abort without retry."""
        # Create event without bevy_event_id
        event_no_config = Event.objects.create(
            organizer=self.organizer,
            name="No Config Event",
            slug="no-config-event",
            date_from="2025-12-01",
        )

        order = Order.objects.create(
            event=event_no_config,
            email="test@example.com",
            status=Order.STATUS_PAID,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="attendee@example.com",
        )

        # Execute task - should not raise, just return
        result = sync_attendee_to_bevy(event_no_config.pk, position.pk, "register")

        # Task should return None (no exception, no retry)
        assert result is None

    def test_sync_attendee_missing_email_skips(self):
        """Test that position without email is skipped gracefully."""
        order = Order.objects.create(
            event=self.event,
            email="",  # No order email
            status=Order.STATUS_PAID,
        )

        position = OrderPosition.objects.create(
            order=order,
            item=None,
            attendee_email="",  # No attendee email
        )

        # Mock requests to ensure they're not called
        with patch("bevy.tasks.requests.post") as mock_post:
            # Execute task
            sync_attendee_to_bevy(self.event.pk, position.pk, "register")

            # Verify API was NOT called
            mock_post.assert_not_called()
