"""Apply the M2 observation-handoff hook to scan_pipeline.py.

Run from the project root:
    python -m scripts.apply_m2_observation_handoff

The script validates every expected source anchor before writing and creates a
backup beside scan_pipeline.py. If the source differs from the expected version,
it exits without modifying the file.
"""

from __future__ import annotations

from pathlib import Path


def replace_exactly_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"Cannot safely patch {label}: expected one matching source block, found {count}. "
            "No files have been modified."
        )
    return source.replace(old, new, 1)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    pipeline_path = root / "backend" / "api" / "services" / "scan_pipeline.py"
    if not pipeline_path.is_file():
        raise FileNotFoundError(f"Could not find {pipeline_path}")

    source = pipeline_path.read_text(encoding="utf-8")
    updated = source

    updated = replace_exactly_once(
        updated,
        "logger = logging.getLogger(__name__)\nDEFAULT_SCAN_TIMEOUT_SECONDS = 180.0\n",
        (
            "logger = logging.getLogger(__name__)\n"
            "ObservationSink = Callable[[list[Observation]], Awaitable[None]]\n"
            "DEFAULT_SCAN_TIMEOUT_SECONDS = 180.0\n"
        ),
        "observation sink type alias",
    )

    old_scan_method = '''    async def scan(self, url: str, framework: str = "gdpr") -> ScanReport:
        """Run a bounded scan, cancelling crawling if the deadline is exceeded."""
        try:
            return await asyncio.wait_for(
                self._scan(url, framework),
                timeout=self.scan_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ScanTimeoutError(
                "Scan exceeded the configured time limit."
            ) from exc
'''
    new_scan_method = '''    async def scan(
        self,
        url: str,
        framework: str = "gdpr",
        *,
        observation_sink: ObservationSink | None = None,
    ) -> ScanReport:
        """Run a bounded scan, optionally staging observations before evaluation."""
        try:
            if observation_sink is None:
                scan_coroutine = self._scan(url, framework)
            else:
                scan_coroutine = self._scan(
                    url,
                    framework,
                    observation_sink=observation_sink,
                )
            return await asyncio.wait_for(
                scan_coroutine,
                timeout=self.scan_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ScanTimeoutError(
                "Scan exceeded the configured time limit."
            ) from exc
'''
    updated = replace_exactly_once(
        updated, old_scan_method, new_scan_method, "bounded scan method"
    )

    updated = replace_exactly_once(
        updated,
        "    async def _scan(self, url: str, framework: str) -> ScanReport:\n",
        (
            "    async def _scan(\n"
            "        self,\n"
            "        url: str,\n"
            "        framework: str,\n"
            "        *,\n"
            "        observation_sink: ObservationSink | None = None,\n"
            "    ) -> ScanReport:\n"
        ),
        "internal scan method signature",
    )

    updated = replace_exactly_once(
        updated,
        '''        if getattr(crawler_result.status, "value", crawler_result.status) != "COMPLETED":
            for rule in rules:
''',
        '''        if getattr(crawler_result.status, "value", crawler_result.status) != "COMPLETED":
            await self._emit_observations(observation_sink, observations)
            for rule in rules:
''',
        "failed-crawler observation staging",
    )

    two_pass_block = '''        if state_diff_rules:
            try:
                two_pass_result = await self._run_two_pass(request.url)
            except Exception:
                two_pass_failed = True
                logger.exception(
                    "Two-pass scan failed for framework=%s", framework_id
                )

        for rule in rules:
'''
    two_pass_replacement = '''        if state_diff_rules:
            try:
                two_pass_result = await self._run_two_pass(request.url)
            except Exception:
                two_pass_failed = True
                logger.exception(
                    "Two-pass scan failed for framework=%s", framework_id
                )

        # Stage the primary crawl and any Accept/Reject observations before
        # rule evaluation so an independent compliance worker can consume them.
        staged_observations = list(observations)
        staged_observations.extend(
            self._all_two_pass_observations(two_pass_result)
        )
        await self._emit_observations(observation_sink, staged_observations)

        for rule in rules:
'''
    updated = replace_exactly_once(
        updated,
        two_pass_block,
        two_pass_replacement,
        "pre-evaluation observation staging",
    )

    old_two_pass_helper = '''    @staticmethod
    def _two_pass_observations(two_pass_result: object | None) -> list[Observation]:
        if two_pass_result is None:
            return []
        combined: list[Observation] = []
        for attribute in ("accept_observations", "reject_observations"):
            observations = getattr(two_pass_result, attribute, []) or []
            combined.extend(observations)
        return combined[:40]
'''
    new_two_pass_helper = '''    @staticmethod
    async def _emit_observations(
        observation_sink: ObservationSink | None,
        observations: list[Observation],
    ) -> None:
        """Await the optional persistence handoff before rule evaluation."""
        if observation_sink is not None:
            await observation_sink(observations)

    @staticmethod
    def _all_two_pass_observations(
        two_pass_result: object | None,
    ) -> list[Observation]:
        """Return every observation from both consent states for staging."""
        if two_pass_result is None:
            return []
        combined: list[Observation] = []
        for attribute in ("accept_observations", "reject_observations"):
            observations = getattr(two_pass_result, attribute, []) or []
            combined.extend(observations)
        return combined

    @staticmethod
    def _two_pass_observations(two_pass_result: object | None) -> list[Observation]:
        # Keep the existing bounded evidence behaviour for manual-review results.
        return ScanPipelineService._all_two_pass_observations(two_pass_result)[:40]
'''
    updated = replace_exactly_once(
        updated,
        old_two_pass_helper,
        new_two_pass_helper,
        "two-pass observation helper",
    )

    # All matching checks have passed. Back up and write only now.
    backup_path = pipeline_path.with_suffix(".py.before_observation_handoff.bak")
    if backup_path.exists():
        raise FileExistsError(
            f"Backup already exists at {backup_path}; inspect it before retrying."
        )
    backup_path.write_text(source, encoding="utf-8")
    pipeline_path.write_text(updated, encoding="utf-8")
    print("Observation-handoff pipeline patch applied successfully.")
    print(f"Backup created: {backup_path}")
    print("No crawler, rule-engine, database-model, or migration files were changed.")


if __name__ == "__main__":
    main()
