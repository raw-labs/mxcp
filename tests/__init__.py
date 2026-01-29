"""Test package marker.

Pytest collects tests fine without this file, but making `tests` a real package
allows shared test helpers (e.g. `tests.sdk.auth.provider_adapter_testkit`) to be
imported reliably.
"""
