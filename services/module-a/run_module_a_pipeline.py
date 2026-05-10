from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PipelineStep:
    name: str
    script: str
    args: List[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Module A raw/interim/cleaned collection pipeline."
    )
    parser.add_argument("--excel", default="Stock_cand.xlsx", help="Path to Stock_cand.xlsx.")
    parser.add_argument("--keys", default="keys.txt", help="Path to keys.txt.")
    parser.add_argument("--listed", default="listed_companies.xlsx", help="Path to listed company master workbook.")
    parser.add_argument("--root", default=".", help="Project root containing company folders.")
    parser.add_argument("--news-only", action="store_true", help="Run only news collection and cleaning.")
    parser.add_argument("--dart-only", action="store_true", help="Run only DART collection and interim building.")
    parser.add_argument("--discover-only", action="store_true", help="Run only related listed-company discovery.")
    parser.add_argument("--skip-setup", action="store_true", help="Skip company folder creation.")
    parser.add_argument("--skip-corp-codes", action="store_true", help="Skip DART corp_code filling.")
    parser.add_argument("--skip-dart", action="store_true", help="Skip all DART steps.")
    parser.add_argument("--skip-news", action="store_true", help="Skip all news steps.")
    parser.add_argument(
        "--with-discovery",
        action="store_true",
        help="Run related listed-company discovery after collection and cleaning.",
    )
    parser.add_argument(
        "--dart-overwrite-interim",
        action="store_true",
        help="Pass --overwrite to build_dart_interim.py.",
    )
    parser.add_argument(
        "--news-overwrite-interim",
        action="store_true",
        help="Pass --overwrite to build_news_interim.py.",
    )
    parser.add_argument(
        "--news-display",
        type=int,
        default=50,
        help="Latest Naver news search result count per company. Max 50.",
    )
    parser.add_argument("--news-days", type=int, default=90, help="Recent-day window for news interim/cleaned.")
    parser.add_argument("--news-max-articles", type=int, default=50, help="Max news articles processed per company.")
    parser.add_argument("--news-timeout", type=int, default=20, help="Article fetch timeout in seconds.")
    parser.add_argument("--discovery-max-depth", type=int, default=1, help="Maximum expansion depth to add.")
    parser.add_argument("--discovery-per-company-limit", type=int, default=5, help="Maximum discoveries per company.")
    parser.add_argument("--discovery-news-threshold", type=float, default=0.9, help="News relation score threshold.")
    parser.add_argument(
        "--discovery-dry-run",
        action="store_true",
        help="Print related-company candidates without modifying Stock_cand.xlsx.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep running later steps even if one step fails.",
    )
    return parser.parse_args()


def resolve_project_path(path_text: str) -> str:
    path = Path(path_text)
    if path.is_absolute():
        return str(path)
    return str(SCRIPT_DIR / path)


def validate_args(args: argparse.Namespace) -> None:
    exclusive_modes = [args.news_only, args.dart_only, args.discover_only]
    if sum(1 for enabled in exclusive_modes if enabled) > 1:
        raise ValueError("--news-only, --dart-only, and --discover-only cannot be used together.")
    if not (1 <= args.news_display <= 50):
        raise ValueError("--news-display must be between 1 and 50.")
    if args.discovery_max_depth < 0:
        raise ValueError("--discovery-max-depth must be zero or greater.")
    if args.discovery_per_company_limit < 1:
        raise ValueError("--discovery-per-company-limit must be at least 1.")


def make_steps(args: argparse.Namespace) -> List[PipelineStep]:
    excel = resolve_project_path(args.excel)
    keys = resolve_project_path(args.keys)
    listed = resolve_project_path(args.listed)
    root = resolve_project_path(args.root)

    run_dart = not args.skip_dart and not args.news_only and not args.discover_only
    run_news = not args.skip_news and not args.dart_only and not args.discover_only
    run_discovery = args.discover_only or (args.with_discovery and not args.news_only and not args.dart_only)
    run_setup = not args.skip_setup and not args.discover_only
    run_corp_codes = run_dart and not args.skip_corp_codes

    steps: List[PipelineStep] = []

    if run_setup:
        steps.append(
            PipelineStep(
                name="Create company folders",
                script="setup_stock_folders.py",
                args=["--excel", excel, "--root", root],
            )
        )

    if run_corp_codes:
        steps.append(
            PipelineStep(
                name="Fill DART corp codes",
                script="fill_corp_codes.py",
                args=["--excel", excel, "--keys", keys, "--cache-dir", str(SCRIPT_DIR / ".cache")],
            )
        )

    if run_dart:
        steps.extend(
            [
                PipelineStep(
                    name="Collect DART periodic raw",
                    script="collect_dart_raw.py",
                    args=["--excel", excel, "--keys", keys, "--root", root],
                ),
                PipelineStep(
                    name="Collect DART equity raw",
                    script="collect_dart_equity_raw.py",
                    args=["--excel", excel, "--keys", keys, "--root", root],
                ),
                PipelineStep(
                    name="Collect DART major issue raw",
                    script="collect_dart_major_reports_raw.py",
                    args=["--excel", excel, "--keys", keys, "--root", root],
                ),
                PipelineStep(
                    name="Build DART interim",
                    script="build_dart_interim.py",
                    args=[
                        "--excel",
                        excel,
                        "--root",
                        root,
                        *(["--overwrite"] if args.dart_overwrite_interim else []),
                    ],
                ),
            ]
        )

    if run_news:
        steps.extend(
            [
                PipelineStep(
                    name="Collect Naver news raw",
                    script="collect_news_raw.py",
                    args=[
                        "--excel",
                        excel,
                        "--keys",
                        keys,
                        "--root",
                        root,
                        "--display",
                        str(args.news_display),
                    ],
                ),
                PipelineStep(
                    name="Build news interim",
                    script="build_news_interim.py",
                    args=[
                        "--excel",
                        excel,
                        "--root",
                        root,
                        "--timeout",
                        str(args.news_timeout),
                        "--days",
                        str(args.news_days),
                        "--max-articles",
                        str(args.news_max_articles),
                        *(["--overwrite"] if args.news_overwrite_interim else []),
                    ],
                ),
                PipelineStep(
                    name="Build news cleaned",
                    script="build_news_cleaned.py",
                    args=[
                        "--excel",
                        excel,
                        "--root",
                        root,
                        "--days",
                        str(args.news_days),
                        "--max-articles",
                        str(args.news_max_articles),
                    ],
                ),
            ]
        )

    if run_discovery:
        steps.append(
            PipelineStep(
                name="Discover related listed companies",
                script="discover_related_companies.py",
                args=[
                    "--excel",
                    excel,
                    "--listed",
                    listed,
                    "--root",
                    root,
                    "--max-depth",
                    str(args.discovery_max_depth),
                    "--per-company-limit",
                    str(args.discovery_per_company_limit),
                    "--news-threshold",
                    str(args.discovery_news_threshold),
                    *(["--dry-run"] if args.discovery_dry_run else []),
                ],
            )
        )

    return steps


def run_step(index: int, total: int, step: PipelineStep) -> int:
    script_path = SCRIPT_DIR / step.script
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    command = [sys.executable, str(script_path), *step.args]
    print(f"\n[{index}/{total}] {step.name}")
    print(" ".join(f'"{part}"' if " " in part else part for part in command))
    completed = subprocess.run(command, cwd=SCRIPT_DIR)
    return completed.returncode


def main() -> int:
    args = parse_args()
    validate_args(args)
    steps = make_steps(args)

    if not steps:
        print("No steps selected.")
        return 0

    failures: List[tuple[str, int]] = []
    for index, step in enumerate(steps, start=1):
        return_code = run_step(index, len(steps), step)
        if return_code != 0:
            failures.append((step.name, return_code))
            print(f"Step failed: {step.name} (exit code {return_code})")
            if not args.continue_on_error:
                break

    if failures:
        print("\nPipeline finished with failures:")
        for name, return_code in failures:
            print(f"- {name}: exit code {return_code}")
        return 1

    print("\nPipeline finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
