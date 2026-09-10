#!/usr/bin/env python3
"""Snapshot GitHub release download counts into a CSV time series.

GitHub only ever reports a *running total* per asset and keeps no history, so
"downloads this week" or an adoption curve are unanswerable after the fact —
the numbers have to be recorded as they go. This script appends one row per
asset per day to stats/downloads.csv, which is the whole point: the counts are
cumulative, but the dated rows let you difference them later.

Re-running on the same day replaces that day's rows rather than duplicating
them, so a manual run alongside the scheduled one is harmless.

Usage:  python3 scripts/collect_stats.py [--repo owner/name] [--out stats]
Auth:   set GITHUB_TOKEN to raise the API rate limit (required in CI).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api.github.com"
FIELDS = ["date", "tag", "published", "asset", "platform", "downloads"]


def _get(url: str) -> list | dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "captura-stats",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_releases(repo: str) -> list[dict]:
    releases, page = [], 1
    while True:  # paginate; a long-lived project outgrows one page
        batch = _get(f"{API}/repos/{repo}/releases?per_page=100&page={page}")
        if not batch:
            break
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return releases


def platform_of(asset_name: str) -> str:
    name = asset_name.lower()
    for key, label in (("macos", "macos"), (".dmg", "macos"),
                       ("windows", "windows"), (".exe", "windows"),
                       ("linux", "linux"), (".tar.gz", "linux")):
        if key in name:
            return label
    return "other"


def rows_for(releases: list[dict], today: str) -> list[dict]:
    rows = []
    for rel in releases:
        if rel.get("draft"):
            continue  # unpublished; nobody can have downloaded it
        for asset in rel.get("assets", []):
            rows.append({
                "date": today,
                "tag": rel.get("tag_name", ""),
                "published": (rel.get("published_at") or "")[:10],
                "asset": asset.get("name", ""),
                "platform": platform_of(asset.get("name", "")),
                "downloads": asset.get("download_count", 0),
            })
    rows.sort(key=lambda r: (r["tag"], r["asset"]))
    return rows


def merge(csv_path: Path, new_rows: list[dict], today: str) -> list[dict]:
    """Existing history minus today's rows, plus today's fresh rows."""
    kept: list[dict] = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as fh:
            kept = [r for r in csv.DictReader(fh) if r.get("date") != today]
    return kept + new_rows


def summarise(rows: list[dict], repo: str, today: str) -> dict:
    """Latest-snapshot totals — the shape a badge or dashboard wants."""
    latest = [r for r in rows if r["date"] == today]
    by_tag: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    for r in latest:
        n = int(r["downloads"])
        by_tag[r["tag"]] = by_tag.get(r["tag"], 0) + n
        by_platform[r["platform"]] = by_platform.get(r["platform"], 0) + n
    return {
        "repo": repo,
        "generated": today,
        "total_downloads": sum(by_tag.values()),
        "by_release": dict(sorted(by_tag.items(), reverse=True)),
        "by_platform": dict(sorted(by_platform.items())),
        "note": "Counts are cumulative totals reported by GitHub, not per-day "
                "downloads. Difference two dated rows in downloads.csv for a rate.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("STATS_REPO", "catzuudon/captura"))
    ap.add_argument("--out", default="stats", type=Path)
    args = ap.parse_args()

    today = date.today().isoformat()
    try:
        releases = fetch_releases(args.repo)
    except urllib.error.HTTPError as exc:
        print(f"error: GitHub API returned {exc.code} for {args.repo}")
        return 1

    new_rows = rows_for(releases, today)
    if not new_rows:
        print("no published release assets found; nothing recorded")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "downloads.csv"
    all_rows = merge(csv_path, new_rows, today)

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    summary = summarise(all_rows, args.repo, today)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"{today}: {len(new_rows)} assets across {len(summary['by_release'])} releases")
    print(f"  total downloads: {summary['total_downloads']}")
    for tag, n in summary["by_release"].items():
        print(f"    {tag:10} {n}")
    for plat, n in summary["by_platform"].items():
        print(f"  {plat:10} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
