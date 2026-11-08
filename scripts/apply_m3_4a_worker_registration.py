"""Safely register crawler/compliance task modules in the shared Celery app.

Run from the project root:
    python -m scripts.apply_m3_4a_worker_registration

The script changes one exact include declaration, after validating its presence,
and creates a backup before writing.
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / "backend" / "infrastructure" / "messaging" / "celery_app.py"
    if not target.is_file():
        raise FileNotFoundError(f"Could not find {target}")

    source = target.read_text(encoding="utf-8")
    old = '    include=["backend.infrastructure.messaging.tasks"],'
    new = '''    include=[
        "backend.infrastructure.messaging.tasks",
        "backend.services.crawler_service.tasks",
        "backend.services.compliance_service.tasks",
    ],'''

    if new in source:
        print("Crawler and compliance task modules are already registered.")
        return

    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            "Could not safely locate the expected Celery include declaration "
            f"(found {count}, expected 1). No file was modified. Inspect celery_app.py."
        )

    backup = target.with_suffix(".py.before_m3_4a_worker_registration.bak")
    if backup.exists():
        raise FileExistsError(
            f"Backup already exists at {backup}. Inspect it before retrying."
        )

    updated = source.replace(old, new, 1)
    backup.write_text(source, encoding="utf-8")
    target.write_text(updated, encoding="utf-8")
    print("Crawler and compliance task modules registered in Celery.")
    print(f"Backup created: {backup}")


if __name__ == "__main__":
    main()
