from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from .client import YettelClient
from .config import AppConfig
from .constants import SUPPORTED_OUTPUT_FORMATS
from .errors import YettelError
from .output import export_usage_result, export_usage_results, print_usage_result, print_usage_results
from .report import BusinessReport, build_business_report
from .storage import UsageHistoryStore


class UserExit(Exception):
    """Raised when the user exits an interactive prompt with Ctrl+C or Ctrl+D."""


def prompt_text(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError) as error:
        raise UserExit from error


def require_credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = getattr(args, "username", None) or os.environ.get("YETTEL_USERNAME")
    password = getattr(args, "password", None) or os.environ.get("YETTEL_PASSWORD")
    if not username:
        username = prompt_text("Yettel username: ")
    if not password:
        try:
            password = getpass.getpass("Yettel password: ")
        except (KeyboardInterrupt, EOFError) as error:
            raise UserExit from error
    if not username or not password:
        raise YettelError("Missing username or password.")
    return username, password


def prompt_menu_choice(client: YettelClient, config: AppConfig) -> str:
    print()
    print("Yettel flotta CLI")
    print(f"Session: {client.session_status_label()}")
    print(f"Cookie file: {config.cookie_file}")
    print(f"Export folder: {config.export_dir}")
    print()
    print("1. Login and save session")
    print("2. Check saved session")
    print("3. List phone numbers")
    print("4. Fetch usage by phone number")
    print("5. Fetch usage by selecting a phone number")
    print("6. Fetch last selected phone again")
    print("7. Fetch all phone numbers and export")
    print("8. Build business report")
    print("9. Open exports folder")
    print("10. Exit")
    return prompt_text("Select option: ")


def prompt_output_format(default: str | None = None) -> str:
    resolved_default = default or "text"
    formats = {"1": "text", "2": "json", "3": "csv", "4": "xlsx", "": resolved_default}
    default_label = {"text": "1", "json": "2", "csv": "3", "xlsx": "4"}[resolved_default]
    print()
    print("Output format")
    print("1. Text")
    print("2. JSON")
    print("3. CSV")
    print("4. XLSX")
    choice = prompt_text(f"Select format [{default_label}]: ")
    return formats.get(choice, resolved_default)


def yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    choice = prompt_text(f"{prompt} [{suffix}]: ").lower()
    if not choice:
        return default
    return choice in {"y", "yes"}


def print_phones(numbers: list[str]) -> None:
    if not numbers:
        print("No phone numbers found.")
        return
    for index, phone in enumerate(numbers, start=1):
        print(f"{index}. {phone}")


def choose_phone(numbers: list[str]) -> str | None:
    query = prompt_text("Filter phone numbers [Enter for all]: ")
    filtered = [phone for phone in numbers if query in phone] if query else numbers
    print_phones(filtered)
    if not filtered:
        return None
    selected = prompt_text("Select phone number: ")
    if selected in filtered:
        return selected
    if selected.isdigit() and 1 <= int(selected) <= len(filtered):
        return filtered[int(selected) - 1]
    print("Invalid phone selection.")
    return None


def save_history_if_requested(config: AppConfig, results, enabled: bool) -> None:
    if not enabled:
        return
    count = UsageHistoryStore(config.db_path).save_results(results if isinstance(results, list) else [results])
    print(f"Saved {count} history rows to {config.db_path}.")


def maybe_open_path(path: Path, *, enabled: bool) -> None:
    if not enabled:
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(path)], check=False)
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]


def resolve_format(args: argparse.Namespace, config: AppConfig, default: str) -> str:
    return args.format or config.default_format or default


def print_report_summary(report: BusinessReport, export_path: Path | None = None) -> None:
    print()
    print("Business report")
    print(f"Phones: {report.phone_count}")
    print(f"Usage rows: {report.row_count}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Changes since last snapshot: {len(report.changes)}")
    if export_path:
        print(f"Exported: {export_path}")

    if report.warnings:
        print()
        print("Warnings")
        for warning in report.warnings[:10]:
            print(f"- {warning.severity.upper()} {warning.phone} {warning.item}: {warning.message}")
        if len(report.warnings) > 10:
            print(f"- ... {len(report.warnings) - 10} more")

    if report.changes:
        print()
        print("Changes")
        for change in report.changes[:10]:
            delta = f" ({change.delta})" if change.delta else ""
            print(f"- {change.phone} {change.item}: {change.previous_available} -> {change.current_available}{delta}")
        if len(report.changes) > 10:
            print(f"- ... {len(report.changes) - 10} more")


def handle_login(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    username, password = require_credentials(args)
    client.login(username, password)
    print(f"Logged in. Session cookies saved to {config.cookie_file}.")
    return 0


def handle_status(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    print(f"Cookie file: {config.cookie_file}")
    print(f"Cookie status: {client.session_status_label()}")
    if args.check_remote:
        print(f"Portal session: {'active' if client.session_alive() else 'expired'}")
    return 0


def handle_phones(args: argparse.Namespace, client: YettelClient) -> int:
    phones = [phone.number for phone in client.phones()]
    if args.format == "json":
        print(json.dumps(phones, ensure_ascii=False, indent=2))
    else:
        for phone in phones:
            print(phone)
    return 0


def handle_usage(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    output_format = resolve_format(args, config, default="text")
    result = client.usage(args.phone)
    if output_format == "xlsx" or args.save:
        path = export_usage_result(result, config.export_dir, output_format)
        print(f"Exported {path}.")
        maybe_open_path(path, enabled=args.open or config.export_open_after_create)
    if output_format != "xlsx":
        print_usage_result(result, output_format)
    save_history_if_requested(config, result, args.history)
    return 0


def handle_all_usage(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    output_format = resolve_format(args, config, default="csv")
    results = client.all_usage()
    if output_format == "xlsx" or args.save:
        path = export_usage_results(results, config.export_dir, output_format)
        print(f"Exported {path}.")
        maybe_open_path(path, enabled=args.open or config.export_open_after_create)
    if output_format != "xlsx":
        print_usage_results(results, output_format)
    save_history_if_requested(config, results, args.history)
    return 0


def handle_report(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    output_format = resolve_format(args, config, default="xlsx")
    store = UsageHistoryStore(config.db_path)
    results = client.all_usage()
    previous_results = store.latest_results([result.phone for result in results])
    report = build_business_report(results, previous_results, config)
    path = export_usage_results(results, config.export_dir, output_format, report=report)
    saved = store.save_results(results)
    print_report_summary(report, path)
    print(f"Saved {saved} history rows to {config.db_path}.")
    maybe_open_path(path, enabled=args.open or config.export_open_after_create)
    return 0


def interactive_menu(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    last_phone: str | None = None
    try:
        while True:
            choice = prompt_menu_choice(client, config)

            try:
                if choice == "1":
                    handle_login(args, client, config)
                    continue

                if choice == "2":
                    print(f"Portal session: {'active' if client.session_alive() else 'expired'}")
                    continue

                if choice == "3":
                    print_phones([phone.number for phone in client.phones()])
                    continue

                if choice == "4":
                    phone = prompt_text("Phone number: ")
                    if not phone:
                        print("Phone number is required.")
                        continue
                    last_phone = phone
                    output_format = prompt_output_format(config.default_format)
                    result = client.usage(phone)
                    if output_format != "xlsx":
                        print_usage_result(result, output_format)
                    if output_format == "xlsx" or yes_no("Export this result?"):
                        path = export_usage_result(result, config.export_dir, output_format)
                        print(f"Exported {path}.")
                        maybe_open_path(path, enabled=config.export_open_after_create)
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, result, True)
                    continue

                if choice == "5":
                    phones = [phone.number for phone in client.phones()]
                    selected_phone = choose_phone(phones)
                    if not selected_phone:
                        continue
                    last_phone = selected_phone
                    print(f"Selected phone: {selected_phone}")
                    output_format = prompt_output_format(config.default_format)
                    result = client.usage(selected_phone)
                    if output_format != "xlsx":
                        print_usage_result(result, output_format)
                    if output_format == "xlsx" or yes_no("Export this result?"):
                        path = export_usage_result(result, config.export_dir, output_format)
                        print(f"Exported {path}.")
                        maybe_open_path(path, enabled=config.export_open_after_create)
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, result, True)
                    continue

                if choice == "6":
                    if not last_phone:
                        print("No last selected phone yet.")
                        continue
                    print(f"Selected phone: {last_phone}")
                    output_format = prompt_output_format(config.default_format)
                    result = client.usage(last_phone)
                    if output_format != "xlsx":
                        print_usage_result(result, output_format)
                    if output_format == "xlsx" or yes_no("Export this result?"):
                        path = export_usage_result(result, config.export_dir, output_format)
                        print(f"Exported {path}.")
                        maybe_open_path(path, enabled=config.export_open_after_create)
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, result, True)
                    continue

                if choice == "7":
                    output_format = prompt_output_format(default=config.default_format or "csv")
                    results = client.all_usage()
                    path = export_usage_results(results, config.export_dir, output_format)
                    print(f"Fetched {len(results)} phone numbers.")
                    print(f"Exported {path}.")
                    maybe_open_path(path, enabled=config.export_open_after_create)
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, results, True)
                    continue

                if choice == "8":
                    handle_report(argparse.Namespace(format=None, open=False), client, config)
                    continue

                if choice == "9":
                    config.export_dir.mkdir(parents=True, exist_ok=True)
                    maybe_open_path(config.export_dir, enabled=True)
                    continue

                if choice in {"10", "q", "quit", "exit"}:
                    return 0

                print("Unknown option.")

            except YettelError as error:
                print(f"error: {error}", file=sys.stderr)
    except UserExit:
        print()
        print("Exiting.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yettel", description="Fetch Yettel portal usage data.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file. Default: .env")
    parser.add_argument("--cookie-file", help="Override saved cookie file path.")
    parser.add_argument("--export-dir", help="Override export folder path.")
    parser.add_argument("--db-path", help="Override SQLite history database path.")
    subparsers = parser.add_subparsers(dest="command")

    login = subparsers.add_parser("login", help="Log in and save session cookies.")
    login.add_argument("--username", help="Yettel username. Defaults to YETTEL_USERNAME.")
    login.add_argument("--password", help="Yettel password. Defaults to YETTEL_PASSWORD.")

    status = subparsers.add_parser("status", help="Show local session status.")
    status.add_argument("--check-remote", action="store_true", help="Make a portal request to verify the session.")

    phones = subparsers.add_parser("phones", help="List phone numbers available in the Usage page dropdown.")
    phones.add_argument("--format", choices=["text", "json"], default="text")

    usage = subparsers.add_parser("usage", help="Fetch usage rows for one phone number.")
    usage.add_argument("phone", help="Phone number as shown in Yettel, e.g. 201234567.")
    usage.add_argument("--format", choices=SUPPORTED_OUTPUT_FORMATS, default=None)
    usage.add_argument("--save", action="store_true", help="Write the result to the export folder.")
    usage.add_argument("--history", action="store_true", help="Save fetched rows to SQLite history.")
    usage.add_argument("--open", action="store_true", help="Open the exported file after creation.")

    all_usage = subparsers.add_parser("all-usage", help="Fetch usage rows for every phone number.")
    all_usage.add_argument("--format", choices=SUPPORTED_OUTPUT_FORMATS, default=None)
    all_usage.add_argument("--save", action="store_true", help="Write the result to the export folder.")
    all_usage.add_argument("--history", action="store_true", help="Save fetched rows to SQLite history.")
    all_usage.add_argument("--open", action="store_true", help="Open the exported file after creation.")

    report = subparsers.add_parser("report", help="Fetch all numbers, save history, export a business report.")
    report.add_argument("--format", choices=SUPPORTED_OUTPUT_FORMATS, default=None)
    report.add_argument("--open", action="store_true", help="Open the exported report after creation.")

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = AppConfig.from_values(
        env_file=args.env_file,
        cookie_file=args.cookie_file,
        export_dir=args.export_dir,
        db_path=args.db_path,
    )
    client = YettelClient(config)

    try:
        if args.command is None:
            return interactive_menu(args, client, config)
        if args.command == "login":
            return handle_login(args, client, config)
        if args.command == "status":
            return handle_status(args, client, config)
        if args.command == "phones":
            return handle_phones(args, client)
        if args.command == "usage":
            return handle_usage(args, client, config)
        if args.command == "all-usage":
            return handle_all_usage(args, client, config)
        if args.command == "report":
            return handle_report(args, client, config)
    except YettelError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except UserExit:
        print()
        print("Exiting.")
        return 130

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
