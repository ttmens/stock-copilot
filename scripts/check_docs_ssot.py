#!/usr/bin/env python3
"""Documentation SSOT hygiene checker — documentation/ layout (v2.1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Issue:
    severity: str
    rule: str
    message: str
    fixable: bool = False


@dataclass
class Report:
    project_root: Path
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: str, rule: str, message: str, fixable: bool = False) -> None:
        self.issues.append(Issue(severity, rule, message, fixable))

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def file_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_version_md(path: Path) -> str | None:
    if not path.is_file():
        return None
    m = re.search(r"\*\*Product version\*\*\s*\|\s*`([^`]+)`", path.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def check_version_consistency(report: Report, root: Path) -> None:
    version_file = root / "documentation" / "VERSION.md"
    expected = parse_version_md(version_file)
    if not expected:
        report.add("error", "version-ssot", "Missing or unparseable documentation/VERSION.md")
        return

    routes = root / "src" / "api" / "routes.py"
    if routes.is_file():
        text = routes.read_text(encoding="utf-8", errors="replace")
        app_m = re.search(r'version="([^"]+)"', text)
        health_m = re.search(r'"version":\s*"([^"]+)"', text)
        if app_m and app_m.group(1) != expected:
            report.add("error", "version-drift", f"FastAPI app version {app_m.group(1)} != VERSION.md {expected}")
        if health_m and health_m.group(1) != expected:
            report.add("error", "version-drift", f"/health version {health_m.group(1)} != VERSION.md {expected}")

    agents = root / "AGENTS.md"
    if agents.is_file() and f"version: {expected}" not in agents.read_text(encoding="utf-8", errors="replace"):
        report.add("warning", "version-drift", f"AGENTS.md frontmatter version != {expected}")


def check_single_current_status(report: Report, root: Path) -> None:
    canonical = root / "documentation" / "reference" / "current-status.md"
    if not canonical.is_file():
        report.add("error", "single-current-status", "Missing documentation/reference/current-status.md")
        return
    ref_dir = root / "documentation" / "reference"
    for p in ref_dir.glob("*CURRENT-STATUS*"):
        if p.resolve() != canonical.resolve():
            report.add("error", "single-current-status", f"Duplicate status doc: {p.relative_to(root)}")


def check_design_tokens(report: Report, root: Path) -> None:
    tokens = root / "documentation" / "design-system" / "tokens.md"
    if not tokens.is_file():
        report.add("error", "design-ssot", "Missing documentation/design-system/tokens.md")


def check_theme_sync(report: Report, root: Path, fix: bool) -> None:
    src = root / "src" / "site" / "theme.css"
    dst = root / "docs" / "assets" / "theme.css"
    if not src.is_file():
        return
    if not dst.is_file():
        report.add("error", "theme-sync", f"Missing published theme: {dst.relative_to(root)}", fixable=True)
        if fix:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return
    if file_hash(src) != file_hash(dst):
        report.add("error", "theme-sync", "src/site/theme.css differs from docs/assets/theme.css", fixable=True)
        if fix:
            shutil.copy2(src, dst)


def check_docs_md_policy(report: Report, root: Path) -> None:
    """docs/ should only contain Pages stubs, not design docs."""
    docs = root / "docs"
    if not docs.is_dir():
        return
    allowed = {"README.md", "UI-UX-Style.md"}
    for md in docs.rglob("*.md"):
        rel = md.relative_to(docs)
        if rel.parts[0] in ("app",):
            continue
        if md.name in allowed:
            if md.name == "UI-UX-Style.md":
                text = md.read_text(encoding="utf-8", errors="replace")
                if "documentation/design-system/tokens.md" not in text:
                    report.add("warning", "deprecated-doc", "UI-UX-Style.md should redirect to documentation/design-system/tokens.md")
            continue
        report.add("error", "docs-md-policy", f"Design markdown not allowed in docs/: {rel} — move to documentation/")


def check_no_legacy_design_tree(report: Report, root: Path) -> None:
    legacy = root / "docs" / "design"
    if legacy.is_dir():
        report.add("error", "legacy-tree", "docs/design/ still exists — should be removed after migration")


def check_ui_ux_stub(report: Report, root: Path, fix: bool) -> None:
    path = root / "docs" / "UI-UX-Style.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if "documentation/design-system/tokens.md" in text:
        return
    report.add("warning", "deprecated-doc", "UI-UX-Style.md missing redirect banner", fixable=True)
    if fix:
        path.write_text(
            "> **已废弃** — 视觉 SSOT: [documentation/design-system/tokens.md](../documentation/design-system/tokens.md)\n",
            encoding="utf-8",
        )


def run_checks(project_root: Path, fix: bool) -> Report:
    report = Report(project_root=project_root.resolve())
    root = report.project_root

    if not (root / "documentation").is_dir():
        report.add("error", "docs-root", "Missing documentation/ directory")
        return report

    check_version_consistency(report, root)
    check_single_current_status(report, root)
    check_design_tokens(report, root)
    check_theme_sync(report, root, fix)
    check_docs_md_policy(report, root)
    check_no_legacy_design_tree(report, root)
    check_ui_ux_stub(report, root, fix)
    _check_phase_g_docs(report, root)

    return report


def _check_phase_g_docs(report: Report, root: Path) -> None:
    required = [
        "documentation/explanation/phase-g-product-spec.md",
        "documentation/reference/knowledge-base-schema.md",
        "documentation/reference/recommendation-engine.md",
        "documentation/reference/monitoring-schedule.md",
        "documentation/reference/ui-phase-g.md",
        "documentation/archive/phase-plans/17-PHASE-G-PLAN.md",
    ]
    for rel in required:
        if not (root / rel).is_file():
            report.add("error", "phase-g-docs", f"Missing Phase G doc: {rel}")


def print_report(report: Report, as_json: bool) -> None:
    if as_json:
        payload = {
            "ok": report.ok,
            "project_root": str(report.project_root),
            "issues": [
                {"severity": i.severity, "rule": i.rule, "message": i.message, "fixable": i.fixable}
                for i in report.issues
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"Docs hygiene: {report.project_root}")
    for i in report.issues:
        icon = {"error": "FAIL", "warning": "WARN", "info": "OK"}.get(i.severity, "•")
        print(f"  [{icon}] [{i.rule}] {i.message}")
    print("Result:", "PASS" if report.ok else "FAIL")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check documentation SSOT hygiene (documentation/)")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--fix", action="store_true", help="Apply safe auto-fixes")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_checks(args.project_root.resolve(), args.fix)
    print_report(report, args.json)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
