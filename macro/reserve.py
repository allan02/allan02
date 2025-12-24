#!/usr/bin/env python3
"""
Futsal reservation helper (template).

Safety defaults:
- Does NOT click the final confirmation/payment button unless --confirm is passed
  and config.reservation.confirm_flag_required is true.

You MUST adapt selectors in config JSON to match the target site.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().isoformat(timespec="seconds")


def _mkdirp(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _log(msg: str) -> None:
    print(f"[{_iso_now()}] {msg}", flush=True)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _wait_until(open_at_iso: Optional[str]) -> None:
    """
    Wait until an ISO timestamp (UTC or with offset). If None, no wait.
    """
    if not open_at_iso:
        return
    try:
        target = datetime.fromisoformat(open_at_iso)
    except ValueError as e:
        raise SystemExit(f"Invalid reservation.open_at (expected ISO 8601): {open_at_iso}") from e

    # If naive, assume UTC
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)

    while True:
        now = _now_utc()
        delta = (target.astimezone(timezone.utc) - now).total_seconds()
        if delta <= 0:
            return
        # Sleep adaptively; cap at 10s to be responsive close to open time.
        time.sleep(min(10.0, max(0.2, delta / 4)))


@dataclass(frozen=True)
class RunPaths:
    artifacts_dir: Path
    screenshots_dir: Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Futsal reservation helper (safe template)")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.futsalbase.example.json")),
        help="Path to config JSON",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Allow clicking final confirmation/payment button (if configured)",
    )
    parser.add_argument(
        "--target-index",
        type=int,
        default=0,
        help="Which reservation.targets item to use",
    )
    args = parser.parse_args()

    load_dotenv(Path(__file__).with_name(".env"))

    username = os.getenv("FUTSAL_USERNAME", "").strip()
    password = os.getenv("FUTSAL_PASSWORD", "").strip()
    if not username or not password:
        _log("Missing FUTSAL_USERNAME or FUTSAL_PASSWORD in macro/.env")
        _log("Copy macro/.env.example to macro/.env and fill it.")
        return 2

    config_path = Path(args.config).resolve()
    cfg = _read_json(config_path)

    artifacts_dir = Path(__file__).with_name("artifacts").resolve()
    run_paths = RunPaths(artifacts_dir=artifacts_dir, screenshots_dir=artifacts_dir / "screenshots")
    _mkdirp(run_paths.screenshots_dir)

    headless = _env_bool("HEADLESS", True)
    slow_mo_ms = _env_int("SLOW_MO_MS", 0)
    trace = _env_bool("TRACE", False)

    base_url = cfg.get("base_url", "").rstrip("/")
    paths = cfg.get("paths", {})
    selectors = cfg.get("selectors", {})
    reservation = cfg.get("reservation", {})

    login_path = paths.get("login", "/login")
    login_url = f"{base_url}{login_path}"

    login_sel = (selectors.get("login") or {})
    post_login_marker = selectors.get("post_login_marker")

    # Reservation target
    targets = reservation.get("targets") or []
    if not targets:
        raise SystemExit("config.reservation.targets is empty; fill it first.")
    if args.target_index < 0 or args.target_index >= len(targets):
        raise SystemExit(f"--target-index out of range. targets={len(targets)} index={args.target_index}")
    target = targets[args.target_index]

    dry_run = bool(reservation.get("dry_run", True))
    confirm_flag_required = bool(reservation.get("confirm_flag_required", True))
    open_at = reservation.get("open_at")

    if not dry_run and confirm_flag_required and not args.confirm:
        raise SystemExit("Refusing to run non-dry-run without --confirm (safety default).")

    _log(f"Config: {config_path}")
    _log(f"Headless={headless} slow_mo_ms={slow_mo_ms} trace={trace}")
    if open_at:
        _log(f"Waiting until open_at={open_at} ...")
        _wait_until(open_at)
        _log("Open time reached.")

    # Import Playwright late, so the script can show helpful config errors even if deps missing.
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        _log("Playwright is not installed or not available.")
        _log("Run: python -m pip install -r macro/requirements.txt && python -m playwright install chromium")
        raise

    def shot(page, name: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = run_paths.screenshots_dir / f"{ts}_{name}.png"
        try:
            page.screenshot(path=str(out), full_page=True)
            _log(f"Saved screenshot: {out}")
        except Exception as e:  # noqa: BLE001
            _log(f"Failed to take screenshot: {e}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
        context = browser.new_context()

        if trace:
            context.tracing.start(screenshots=True, snapshots=True, sources=False)

        page = context.new_page()
        page.set_default_timeout(20_000)

        try:
            _log(f"Go to login: {login_url}")
            page.goto(login_url, wait_until="domcontentloaded")

            _log("Fill credentials")
            user_sel = login_sel.get("username")
            pass_sel = login_sel.get("password")
            submit_sel = login_sel.get("submit")
            if not (user_sel and pass_sel and submit_sel):
                raise SystemExit("config.selectors.login.username/password/submit must be set for this site.")

            page.locator(user_sel).fill(username)
            page.locator(pass_sel).fill(password)
            page.locator(submit_sel).click()

            if post_login_marker:
                _log("Waiting for post-login marker")
                page.locator(post_login_marker).first.wait_for(timeout=20_000)
            else:
                _log("No post_login_marker configured; waiting briefly")
                page.wait_for_timeout(1500)

            _log("Login step done.")

            # Navigate to schedule/reservation area (site-specific)
            rsel = (reservation.get("selectors") or {})
            go_to_schedule = rsel.get("go_to_schedule")
            if go_to_schedule:
                _log("Navigating to schedule")
                page.locator(go_to_schedule).first.click()
                page.wait_for_load_state("domcontentloaded")
            else:
                _log("No reservation.selectors.go_to_schedule set; skipping navigation.")

            # Best-effort template steps (must be adapted)
            facility_name = (target.get("facility_name") or "").strip()
            date_str = (target.get("date") or "").strip()
            time_str = (target.get("time") or "").strip()

            if facility_name and rsel.get("facility_search_input") and rsel.get("facility_result_item"):
                _log(f"Selecting facility: {facility_name}")
                page.locator(rsel["facility_search_input"]).fill(facility_name)
                # facility_result_item can be a selector or literal "text=..."
                page.locator(rsel["facility_result_item"]).first.click()

            if date_str and rsel.get("date_picker"):
                _log(f"Setting date: {date_str}")
                page.locator(rsel["date_picker"]).fill(date_str)

            if time_str and rsel.get("time_slot_button"):
                _log(f"Clicking time slot: {time_str}")
                page.locator(rsel["time_slot_button"]).first.click()

            reserve_btn = rsel.get("reserve_button")
            if reserve_btn:
                _log("Clicking reserve button (pre-confirm)")
                page.locator(reserve_btn).first.click()
                page.wait_for_load_state("domcontentloaded")
            else:
                _log("No reservation.selectors.reserve_button set; stopping here.")

            final_btn = rsel.get("final_confirm_button")
            if dry_run:
                _log("DRY RUN: stopping before final confirmation.")
                shot(page, "dry_run_stop")
                _log("You can now complete the final confirmation manually in the opened browser.")
                page.wait_for_timeout(15_000)
            else:
                if not final_btn:
                    raise SystemExit("Non-dry-run requested but final_confirm_button selector is missing.")
                if confirm_flag_required and not args.confirm:
                    raise SystemExit("Non-dry-run requested but --confirm not passed.")
                _log("Clicking final confirmation/payment button")
                page.locator(final_btn).first.click()
                page.wait_for_load_state("networkidle")
                shot(page, "after_confirm")
                _log("Final confirmation clicked.")

            if trace:
                trace_out = run_paths.artifacts_dir / "trace.zip"
                context.tracing.stop(path=str(trace_out))
                _log(f"Saved trace: {trace_out}")

        except (PlaywrightTimeoutError, PlaywrightError, SystemExit) as e:
            _log(f"ERROR: {e}")
            shot(page, "error")
            if trace:
                trace_out = run_paths.artifacts_dir / "trace_error.zip"
                try:
                    context.tracing.stop(path=str(trace_out))
                    _log(f"Saved trace: {trace_out}")
                except Exception:  # noqa: BLE001
                    pass
            return 1
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

