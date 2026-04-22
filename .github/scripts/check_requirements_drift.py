#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_FILES = (
    "requirements.txt",
    "requirements-pg.txt",
    "requirements-mariadb.txt",
)
DRIFT_EXIT_CODE = 2
MAX_ITEMS_PER_SECTION = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare committed Poetry exports with freshly generated requirements files."
        )
    )
    parser.add_argument(
        "--expected-dir",
        type=Path,
        required=True,
        help="Directory containing the committed requirements files.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        required=True,
        help="Directory containing freshly generated requirements files.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write a markdown report.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=list(DEFAULT_FILES),
        help="Specific requirement files to compare.",
    )
    return parser.parse_args()


def read_requirements(path: Path) -> dict[str, frozenset[str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    records: dict[str, set[str]] = {}
    current: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        continued = stripped.endswith("\\")
        current.append(stripped[:-1].rstrip() if continued else stripped)

        if continued:
            continue

        requirement, hashes = normalize_record(" ".join(current))
        records.setdefault(requirement, set()).update(hashes)
        current = []

    if current:
        requirement, hashes = normalize_record(" ".join(current))
        records.setdefault(requirement, set()).update(hashes)

    return {key: frozenset(sorted(values)) for key, values in records.items()}


def normalize_record(record: str) -> tuple[str, tuple[str, ...]]:
    hashes = tuple(sorted(set(re.findall(r"--hash=\S+", record))))
    requirement = re.sub(r"\s*--hash=\S+", "", record).strip()
    requirement = re.sub(r"\s*;\s*", " ; ", requirement)
    requirement = re.sub(r"\s+", " ", requirement).strip()
    return requirement, hashes


def compare_file(expected_path: Path, generated_path: Path) -> dict[str, object]:
    expected = read_requirements(expected_path)
    generated = read_requirements(generated_path)

    only_in_expected = sorted(set(expected) - set(generated))
    only_in_generated = sorted(set(generated) - set(expected))
    hash_changes = sorted(
        requirement
        for requirement in set(expected).intersection(generated)
        if expected[requirement] != generated[requirement]
    )

    return {
        "expected_path": expected_path,
        "generated_path": generated_path,
        "only_in_expected": only_in_expected,
        "only_in_generated": only_in_generated,
        "hash_changes": hash_changes,
        "drift": bool(only_in_expected or only_in_generated or hash_changes),
    }


def summarize_items(items: list[str]) -> list[str]:
    if len(items) <= MAX_ITEMS_PER_SECTION:
        return items

    visible = items[:MAX_ITEMS_PER_SECTION]
    visible.append(f"... and {len(items) - MAX_ITEMS_PER_SECTION} more")
    return visible


def format_report(comparisons: list[dict[str, object]], had_errors: bool) -> str:
    drift_results = [result for result in comparisons if result["drift"]]

    if not drift_results and not had_errors:
        return (
            "# Requirements export check\n\n"
            "No drift detected between the committed `requirements*.txt` files and "
            "fresh Poetry exports.\n"
        )

    lines = [
        "# Requirements export check",
        "",
    ]

    if drift_results:
        lines.extend(
            [
                "The committed exported dependency files do not match a fresh Poetry export.",
                "",
                "Run the following command and commit the result:",
                "",
                "```bash",
                "make update-requirements",
                "```",
                "",
            ]
        )

    for result in comparisons:
        expected_path = Path(result["expected_path"])
        lines.append(f"## `{expected_path.name}`")

        if "error" in result:
            lines.append(f"- Error: {result['error']}")
            lines.append("")
            continue

        if not result["drift"]:
            lines.append("- No drift detected.")
            lines.append("")
            continue

        only_in_generated = summarize_items(list(result["only_in_generated"]))
        only_in_expected = summarize_items(list(result["only_in_expected"]))
        hash_changes = summarize_items(list(result["hash_changes"]))

        if only_in_generated:
            lines.append("- Missing from committed export:")
            for item in only_in_generated:
                lines.append(f"  - `{item}`")

        if only_in_expected:
            lines.append("- Present in committed export but not in regenerated export:")
            for item in only_in_expected:
                lines.append(f"  - `{item}`")

        if hash_changes:
            lines.append("- Requirement hashes changed:")
            for item in hash_changes:
                lines.append(f"  - `{item}`")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    comparisons: list[dict[str, object]] = []
    had_errors = False
    had_drift = False

    for filename in args.files:
        expected_path = args.expected_dir / filename
        generated_path = args.generated_dir / filename

        try:
            comparison = compare_file(expected_path, generated_path)
        except Exception as exc:  # pragma: no cover - defensive path for CI diagnostics
            had_errors = True
            comparison = {
                "expected_path": expected_path,
                "generated_path": generated_path,
                "drift": True,
                "error": str(exc),
            }
        else:
            had_drift = had_drift or bool(comparison["drift"])

        comparisons.append(comparison)

    report = format_report(comparisons, had_errors)
    sys.stdout.write(report)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")

    if had_errors or had_drift:
        return DRIFT_EXIT_CODE

    return 0


if __name__ == "__main__":
    sys.exit(main())
