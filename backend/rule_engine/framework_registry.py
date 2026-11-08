"""Allowlisted mapping from public framework IDs to local YAML rule files.

Task/API input may select a registered ID, but it can never supply a path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FRAMEWORK_RULE_FILES: dict[str, Path] = {
    "gdpr": PROJECT_ROOT / "rules" / "gdpr" / "rules.yaml",
}


class UnsupportedFrameworkError(ValueError):
    """Raised when a framework ID is not present in the trusted registry."""


class FrameworkRegistry:
    """Resolve normalized framework IDs using a trusted in-process mapping."""

    def __init__(
        self,
        rule_files: Mapping[str, str | Path] | None = None,
    ) -> None:
        source = DEFAULT_FRAMEWORK_RULE_FILES if rule_files is None else rule_files
        self._rule_files = {
            str(key).strip().lower(): Path(value)
            for key, value in source.items()
        }

    def resolve(self, framework_id: str) -> tuple[str, Path]:
        if not isinstance(framework_id, str):
            raise UnsupportedFrameworkError("Unsupported compliance framework.")

        normalized = framework_id.strip().lower()
        # The allowlist lookup, not path sanitization, is the security boundary.
        rule_path = self._rule_files.get(normalized)
        if not normalized or rule_path is None:
            raise UnsupportedFrameworkError("Unsupported compliance framework.")
        return normalized, rule_path

    @property
    def rule_files(self) -> dict[str, Path]:
        """Return a copy so callers cannot mutate the registry accidentally."""
        return dict(self._rule_files)
