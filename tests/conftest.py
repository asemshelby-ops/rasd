"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_pin_unless_a_test_asks_for_one(monkeypatch):
    """The operator and supervisor pages ask for a PIN. Tests that are not about the PIN turn it off."""
    monkeypatch.setenv("RASD_PIN", "off")
