#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CRITICAL_VULNERABILITIES_EXIT_CODE = 2
DEFAULT_GLOB = "*.json"
MAX_ITEMS_PER_SECTION = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect CycloneDX SBOM files and report vulnerabilities, with a dedicated "
            "exit code when critical vulnerabilities are present."
        )
    )
    parser.add_argument(
        "--sbom-dir",
        type=Path,
        required=True,
        help="Directory containing SBOM JSON artifacts.",
    )
    parser.add_argument(
        "--glob",
        default=DEFAULT_GLOB,
        help="Glob pattern used to select SBOM files within --sbom-dir.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the markdown report.",
    )
    return parser.parse_args()


def severity_rank(severity: str) -> int:
    order = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "unknown": 1,
        "none": 0,
    }
    return order.get(severity.lower(), 1)


def normalize_severity(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return value.strip().upper() or "UNKNOWN"


def highest_severity(vulnerability: dict[str, Any]) -> str:
    ratings = vulnerability.get("ratings", [])
    if not isinstance(ratings, list) or not ratings:
        return "UNKNOWN"

    severities: list[str] = []
    for rating in ratings:
        if not isinstance(rating, dict):
            continue
        severities.append(normalize_severity(rating.get("severity")))

    if not severities:
        return "UNKNOWN"

    return max(severities, key=lambda item: severity_rank(item))


def summarize_items(items: list[str], limit: int = MAX_ITEMS_PER_SECTION) -> list[str]:
    if len(items) <= limit:
        return items
    visible = items[:limit]
    visible.append(f"... and {len(items) - limit} more")
    return visible


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def extract_reference_link(vulnerability: dict[str, Any]) -> str:
    references = vulnerability.get("references", [])
    if isinstance(references, list):
        for reference in references:
            if isinstance(reference, dict):
                url = reference.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()

    advisories = vulnerability.get("advisories", [])
    if isinstance(advisories, list):
        for advisory in advisories:
            if isinstance(advisory, dict):
                url = advisory.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()

    source = vulnerability.get("source")
    if isinstance(source, dict):
        url = source.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()

    return ""


def read_sbom(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def component_name_by_bom_ref(payload: dict[str, Any]) -> dict[str, str]:
    components = payload.get("components", [])
    if not isinstance(components, list):
        return {}

    mapping: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            continue

        ref = component.get("bom-ref")
        if not isinstance(ref, str) or not ref:
            continue

        name = component.get("name")
        version = component.get("version")
        if isinstance(name, str) and isinstance(version, str) and version:
            mapping[ref] = f"{name}@{version}"
        elif isinstance(name, str) and name:
            mapping[ref] = name
        else:
            mapping[ref] = ref
    return mapping


def format_vulnerability_entry(
    vulnerability: dict[str, Any], component_map: dict[str, str]
) -> str:
    vuln_id = str(vulnerability.get("id") or "UNKNOWN-ID")
    severity = highest_severity(vulnerability)
    affects = vulnerability.get("affects", [])

    affected_components: list[str] = []
    if isinstance(affects, list):
        for item in affects:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref")
            if isinstance(ref, str) and ref:
                affected_components.append(component_map.get(ref, ref))

    if not affected_components:
        return f"`{vuln_id}` ({severity})"

    unique_components = sorted(set(affected_components))
    component_text = ", ".join(unique_components)
    return f"`{vuln_id}` ({severity}) in `{component_text}`"


def vulnerability_table_row(
    vulnerability: dict[str, Any], component_map: dict[str, str]
) -> dict[str, str]:
    vuln_id = str(vulnerability.get("id") or "UNKNOWN-ID")
    severity = highest_severity(vulnerability)
    affects = vulnerability.get("affects", [])

    affected_components: list[str] = []
    if isinstance(affects, list):
        for item in affects:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref")
            if isinstance(ref, str) and ref:
                affected_components.append(component_map.get(ref, ref))

    components = (
        ", ".join(sorted(set(affected_components))) if affected_components else "-"
    )
    link = extract_reference_link(vulnerability)
    link_md = f"[link]({link})" if link else "-"

    return {
        "id": markdown_escape(vuln_id),
        "severity": markdown_escape(severity),
        "components": markdown_escape(components),
        "link": link_md,
    }


def inspect_sbom(path: Path) -> dict[str, Any]:
    payload = read_sbom(path)
    component_map = component_name_by_bom_ref(payload)
    vulnerabilities = payload.get("vulnerabilities", [])

    if not isinstance(vulnerabilities, list):
        vulnerabilities = []

    by_severity: dict[str, int] = {}
    critical_entries: list[str] = []
    critical_rows: list[dict[str, str]] = []

    for vulnerability in vulnerabilities:
        if not isinstance(vulnerability, dict):
            continue

        severity = highest_severity(vulnerability)
        by_severity[severity] = by_severity.get(severity, 0) + 1
        if severity == "CRITICAL":
            critical_entries.append(
                format_vulnerability_entry(vulnerability, component_map)
            )
            critical_rows.append(vulnerability_table_row(vulnerability, component_map))

    return {
        "path": path,
        "total": sum(by_severity.values()),
        "by_severity": by_severity,
        "critical": sorted(set(critical_entries)),
        "critical_count": len(critical_entries),
        "critical_rows": critical_rows,
    }


def format_report(results: list[dict[str, Any]], had_errors: bool) -> str:
    total_vulns = sum(int(result["total"]) for result in results)
    total_critical = sum(int(result["critical_count"]) for result in results)

    lines = [
        "# SBOM vulnerability check",
        "",
    ]

    if had_errors:
        lines.extend(
            [
                ":warning: The SBOM vulnerability check encountered parsing errors.",
                "",
            ]
        )

    if total_critical == 0 and not had_errors:
        lines.extend(
            [
                ":white_check_mark: No critical vulnerabilities detected across SBOM artifacts.",
                "",
            ]
        )
    elif total_critical > 0:
        lines.extend(
            [
                f":warning: Found **{total_critical} critical** vulnerability entries across SBOM artifacts.",
                "",
            ]
        )

    lines.append(f"Total vulnerabilities observed: **{total_vulns}**")
    lines.append("")

    for result in results:
        sbom_path = Path(result["path"])
        lines.append(f"## `{sbom_path.name}`")

        if "error" in result:
            lines.append(f"- Error: {result['error']}")
            lines.append("")
            continue

        severity_counts = result["by_severity"]
        if severity_counts:
            ordered_levels = sorted(
                severity_counts.keys(),
                key=lambda level: severity_rank(level),
                reverse=True,
            )
            summary = ", ".join(
                f"{level}: {severity_counts[level]}" for level in ordered_levels
            )
            lines.append(f"- Severity breakdown: {summary}")
        else:
            lines.append("- No vulnerabilities listed in this SBOM.")

        critical_rows = list(result.get("critical_rows", []))
        if critical_rows:
            lines.append("- Critical vulnerabilities:")
            lines.append("")
            lines.append("| Vulnerability | Severity | Component(s) | Reference |")
            lines.append("|---|---|---|---|")
            for row in critical_rows[:MAX_ITEMS_PER_SECTION]:
                lines.append(
                    f"| `{row['id']}` | {row['severity']} | `{row['components']}` | {row['link']} |"
                )
            if len(critical_rows) > MAX_ITEMS_PER_SECTION:
                lines.append(
                    f"| ... | ... | ... | ... and {len(critical_rows) - MAX_ITEMS_PER_SECTION} more |"
                )

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    if not args.sbom_dir.exists():
        raise FileNotFoundError(f"SBOM directory does not exist: {args.sbom_dir}")

    paths = sorted(args.sbom_dir.glob(args.glob))
    if not paths:
        raise FileNotFoundError(
            f"No SBOM files matched pattern {args.glob!r} in {args.sbom_dir}"
        )

    results: list[dict[str, Any]] = []
    had_errors = False
    has_critical = False

    for path in paths:
        try:
            result = inspect_sbom(path)
        except Exception as exc:  # pragma: no cover - defensive CI diagnostics
            had_errors = True
            result = {"path": path, "error": str(exc), "total": 0, "critical_count": 0}
        else:
            has_critical = has_critical or bool(result["critical_count"])

        results.append(result)

    report = format_report(results, had_errors=had_errors)
    sys.stdout.write(report)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")

    if had_errors:
        return 1
    if has_critical:
        return CRITICAL_VULNERABILITIES_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())
