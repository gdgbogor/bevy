# Bevy to Pretix Integration (Pretix Plugin)

This project is a Pretix plugin intended to automatically inject data (e.g. attendees, event registrations) into the Bevy platform via the Bevy API. 
The plugin is currently in its initial scaffolding stage.

## Key Files
- `pyproject.toml` and `setup.py`: Packaging configuration indicating the entry point `bevy:PretixPluginMeta` for Pretix.
- `bevy/apps.py`: Contains the `PluginApp` which inherits from `PluginConfig`. Defines the `PretixPluginMeta` with the category "INTEGRATION" and compatibility `pretix>=2.7.0`.
- `bevy/signals.py`: Intended for registering Pretix signal receivers (e.g., ticket purchased, order placed) to trigger synchronization. Currently empty.
- `README.rst`: Details development setup instructions (using `python setup.py develop` and `make`).

## Future Implementation Roadmap
Given its purpose to integrate with Bevy, the plugin will likely need to:
1. Listen to Pretix signals in `signals.py` such as `pretix.base.signals.order_placed` or `pretix.base.signals.order_paid`.
2. Communicate with the external `bevy-api` wrapper (documented in the `bevy_api_reference` memory) to register attendees or check them in.
3. Manage settings via `settings_links` to configure the Bevy chapter ID, event ID, or API URL for a specific Pretix event.

*Note: As of now, the core business logic in the plugin has not been implemented.*