from __future__ import annotations

import pytest

from backend.main import _configured_frontend_origins


def test_cors_configuration_requires_explicit_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FRONTEND_ORIGINS', 'https://brandguard.example, https://preview.example')

    assert _configured_frontend_origins() == [
        'https://brandguard.example',
        'https://preview.example',
    ]


def test_cors_configuration_rejects_wildcard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FRONTEND_ORIGINS', '*')

    with pytest.raises(RuntimeError, match='explicit origins'):
        _configured_frontend_origins()
