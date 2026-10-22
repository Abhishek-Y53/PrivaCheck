"""Run consent-sensitive checks against pre-consent evidence only.

Run from the PrivaCheck repository root:
    python -m backend.rule_engine.run_gdpr_preconsent_check

The rule set remains YAML-driven. This diagnostic selects rules whose YAML
applicability explicitly requires consent_phase == 'before_consent'.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.crawler.browser import BrowserManager
from backend.crawler.two_pass import TwoPassRunner
from backend.rule_engine.engine import RuleEngine
from backend.rule_engine.loader import RuleLoader
from backend.schemas.core import CrawlerStatus, Observation


def _conditions_include_before_consent(applicability: Any) -> bool:
    """Return True when applicability declares the before-consent phase."""
    if applicability is None:
        return False

    conditions = applicability.conditions
    condition_groups = (
        getattr(conditions, "all", None) or [],
        getattr(conditions, "any", None) or [],
        getattr(conditions, "not_", None) or [],
    )

    return any(
        condition.field == "consent_phase"
        and condition.operator == "equals"
        and condition.value == "before_consent"
        for group in condition_groups
        for condition in group
    )


def _get_before_consent_observations(
    observations: list[Observation],
) -> list[Observation]:
    return [
        observation
        for observation in observations
        if observation.data.get("consent_phase") == "before_consent"
    ]


def _normalise_url(value: str) -> str:
    url = value.strip()
    if not url:
        raise ValueError("A website URL is required.")
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


async def main() -> None:
    try:
        url = _normalise_url(input("Enter website URL: "))
    except ValueError as exc:
        print(f"Invalid URL: {exc}")
        return

    rules_path = Path("rules/gdpr/rules.yaml")
    loader = RuleLoader()

    print("\n========== LOADING PRE-CONSENT RULES ==========")
    try:
        all_rules = loader.load(rules_path)
    except Exception as exc:
        print(f"Could not load rules from {rules_path}: {exc}")
        return

    rules = [
        rule
        for rule in all_rules
        if rule.evaluator == "declarative"
        and _conditions_include_before_consent(
            getattr(rule, "applicability", None)
        )
    ]

    if not rules:
        print("No pre-consent rules found in rules/gdpr/rules.yaml.")
        print(
            "Add the pre-consent rules with applicability conditions on "
            "consent_phase == before_consent, then rerun this diagnostic."
        )
        return

    for rule in rules:
        print(f"  {rule.id}: {rule.name}")

    manager = BrowserManager(headless=True)
    context = None
    page = None

    try:
        print("\n========== RUNNING ISOLATED ACCEPT/REJECT SCAN ==========")
        await manager.start()
        context, page = await manager.create_context_and_page()

        two_pass = await TwoPassRunner(
            page,
            context,
            url,
            wait_ms=3000,
            consent_wait_ms=1500,
        ).run()

        print(f"Scan status: {two_pass.status.value}")
        if two_pass.error:
            print(f"Scan error: {two_pass.error}")

        for label, snapshot in (
            ("ACCEPT", two_pass.accept),
            ("REJECT", two_pass.reject),
        ):
            if snapshot is None:
                print(f"{label} interaction: unavailable")
                continue
            print(
                f"{label} pass: status={snapshot.status.value}, "
                f"interaction={snapshot.interaction.status}, "
                f"matched={snapshot.interaction.matched_text!r}"
            )
            if snapshot.interaction.error:
                print(f"  interaction detail: {snapshot.interaction.error}")

        # Use the Reject pass's fresh, pre-click state as the primary evidence.
        # Fall back to the Accept pass only if the Reject pass has no such data.
        pre_consent_observations = (
            _get_before_consent_observations(
                two_pass.reject.observations
            )
            if two_pass.reject is not None
            else []
        )
        if not pre_consent_observations and two_pass.accept is not None:
            pre_consent_observations = _get_before_consent_observations(
                two_pass.accept.observations
            )

        print("\n========== PRE-CONSENT EVIDENCE ==========")
        print(f"Observations collected: {len(pre_consent_observations)}")

        from collections import Counter

        print(
            "By category:",
            dict(Counter(obs.category for obs in pre_consent_observations)),
        )

        print("\n========== LAYOUT EVIDENCE ==========")

        layout_observations = [
            obs
            for obs in pre_consent_observations
            if obs.category == "dom_layout"
        ]

        if not layout_observations:
            print("No dom_layout observations found.")

        for obs in layout_observations:
            print({
                "source_url": obs.source_url,
                "body_overflow_y": obs.data.get("body_overflow_y"),
                "fixed_element_count": obs.data.get(
                    "fixed_element_count"
                ),
                "consent_related_fixed_element_count": obs.data.get(
                    "consent_related_fixed_element_count"
                ),
            })

        if two_pass.status == CrawlerStatus.FAILED:
            print("\n========== VISIBLE BUTTON INVENTORY ==========")

            visible_buttons = [
                obs
                for obs in pre_consent_observations
                if obs.category == "dom_button"
                and obs.data.get("visible") is True
            ]

            if not visible_buttons:
                print("No visible buttons were collected.")

            for obs in visible_buttons:
                data = obs.data
                print({
                    "text": data.get("text"),
                    "aria_label": data.get("aria_label"),
                    "role": data.get("role"),
                    "id": data.get("id"),
                    "class_name": data.get("class_name"),
                })
            print("\nTwo-pass scan failed; skipping rule evaluation.")
            return

        print("\n========== EVALUATING PRE-CONSENT RULES ==========")
        results = RuleEngine().evaluate_rules(
            rules,
            pre_consent_observations,
        )

        counts: Counter[str] = Counter()
        for result in results:
            status = result.status.value
            counts[status] += 1
            print(f"\nRule       : {result.check_id}")
            print(f"Name       : {result.name}")
            print(f"Status     : {status}")
            print(f"Severity   : {result.severity.value}")
            print(f"Confidence : {result.confidence:.2f}")
            print(f"Evidence   : {len(result.evidence)}")
            print(f"Explanation: {result.explanation}")
            if result.recommendation:
                print(f"Recommendation: {result.recommendation}")
            for evidence in result.evidence[:3]:
                print(
                    f"  - {evidence.category}: "
                    f"{evidence.data}"
                )

        print("\n========== SUMMARY ==========")
        print(f"Pre-consent rules evaluated: {len(results)}")
        for status, count in sorted(counts.items()):
            print(f"{status}: {count}")
        print("\n========== PRE-CONSENT DIAGNOSTIC COMPLETE ==========")

    except Exception as exc:
        print(f"Pre-consent diagnostic failed: {exc}")
        raise
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
