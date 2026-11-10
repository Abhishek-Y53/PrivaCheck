"""Locally manage platform admission until audited admin APIs ship (Phase B).

Only run from a trusted shell with database credentials. This is NOT a public API.
Usage: python -m backend.scripts.manage_allowlist email add someone@gmail.com
       python -m backend.scripts.manage_allowlist domain disable iiitg.ac.in
"""
from __future__ import annotations

import argparse
import re
from sqlalchemy import select

from backend.api.services.auth_service import normalize_email
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.session import SessionLocal

DOMAIN = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


def manage(selector_type: str, action: str, value: str) -> None:
    model = PlatformAccessEmail if selector_type == "email" else PlatformAccessDomain
    value = normalize_email(value) if selector_type == "email" else value.strip().lower()
    if selector_type == "domain" and not DOMAIN.fullmatch(value):
        raise ValueError("Expected an exact DNS domain, not a wildcard or suffix pattern.")
    column = model.email if selector_type == "email" else model.domain
    with SessionLocal() as db:
        with db.begin():
            item = db.scalar(select(model).where(column == value).with_for_update())
            if action == "add":
                if item is None:
                    db.add(model(**{selector_type if selector_type == "email" else "domain": value}))
                else:
                    item.is_active = True
            elif action == "disable":
                if item is None:
                    raise ValueError("No matching allowlist entry exists.")
                item.is_active = False
    print(f"{selector_type} {value}: {action} complete (sessions rechecked on next request)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("type", choices=["email", "domain"])
    parser.add_argument("action", choices=["add", "disable"])
    parser.add_argument("value")
    args = parser.parse_args()
    manage(args.type, args.action, args.value)
