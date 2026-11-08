from pathlib import Path

import pytest

from backend.rule_engine.framework_registry import (
    FrameworkRegistry,
    UnsupportedFrameworkError,
)


def test_registry_normalizes_registered_framework_id():
    expected = Path("rules/gdpr/rules.yaml")
    registry = FrameworkRegistry({"gdpr": expected})

    framework_id, path = registry.resolve(" GDPR ")

    assert framework_id == "gdpr"
    assert path == expected


@pytest.mark.parametrize("value", ["../../private", "", "unknown", "gdpr/rules.yaml"])
def test_registry_rejects_unregistered_ids_without_treating_them_as_paths(value):
    registry = FrameworkRegistry({"gdpr": Path("rules/gdpr/rules.yaml")})

    with pytest.raises(UnsupportedFrameworkError):
        registry.resolve(value)
