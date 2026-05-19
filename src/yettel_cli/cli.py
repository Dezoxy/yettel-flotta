from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Iterable

from .client import YettelClient
from .config import AppConfig
from .errors import YettelError
from .output import export_usage_result, export_usage_results, print_usage_result, print_usage_results
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
    print("6. Fetch all phone numbers and export")
    print("7. Exit")
    return prompt_text("Select option: ")


def prompt_output_format(default: str = "text") -> str:
    formats = {"1": "text", "2": "json", "3": "csv", "": default}
    default_label = {"text": "1", "json": "2", "csv": "3"}[default]
    print()
    print("Output format")
    print("1. Text")
    print("2. JSON")
    print("3. CSV")
    choice = prompt_text(f"Select format [{default_label}]: ")
    return formats.get(choice, default)


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


def save_history_if_requested(config: AppConfig, results, enabled: bool) -> None:
    if not enabled:
        return
    count = UsageHistoryStore(config.db_path).save_results(results if isinstance(results, list) else [results])
    print(f"Saved {count} history rows to {config.db_path}.")


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
    result = client.usage(args.phone)
    print_usage_result(result, args.format)
    if args.save:
        path = export_usage_result(result, config.export_dir, args.format)
        print(f"Exported {path}.")
    save_history_if_requested(config, result, args.history)
    return 0


def handle_all_usage(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
    results = client.all_usage()
    print_usage_results(results, args.format)
    if args.save:
        path = export_usage_results(results, config.export_dir, args.format)
        print(f"Exported {path}.")
    save_history_if_requested(config, results, args.history)
    return 0


def interactive_menu(args: argparse.Namespace, client: YettelClient, config: AppConfig) -> int:
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
                    output_format = prompt_output_format()
                    result = client.usage(phone)
                    print_usage_result(result, output_format)
                    if yes_no("Export this result?"):
                        print(f"Exported {export_usage_result(result, config.export_dir, output_format)}.")
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, result, True)
                    continue

                if choice == "5":
                    phones = [phone.number for phone in client.phones()]
                    print_phones(phones)
                    if not phones:
                        continue
                    selected = prompt_text("Select phone number: ")
                    if not selected.isdigit() or not 1 <= int(selected) <= len(phones):
                        print("Invalid phone selection.")
                        continue
                    output_format = prompt_output_format()
                    result = client.usage(phones[int(selected) - 1])
                    print_usage_result(result, output_format)
                    if yes_no("Export this result?"):
                        print(f"Exported {export_usage_result(result, config.export_dir, output_format)}.")
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, result, True)
                    continue

                if choice == "6":
                    output_format = prompt_output_format(default="csv")
                    results = client.all_usage()
                    path = export_usage_results(results, config.export_dir, output_format)
                    print(f"Fetched {len(results)} phone numbers.")
                    print(f"Exported {path}.")
                    if yes_no("Save to SQLite history?"):
                        save_history_if_requested(config, results, True)
                    continue

                if choice in {"7", "q", "quit", "exit"}:
                    return 0

                print("Unknown option.")

            except YettelError as error:
                print(f"error: {error}", file=sys.stderr)
    except UserExit:
        print()
        print("Exiting.")
        return 130


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
    usage.add_argument("--format", choices=["text", "json", "csv"], default="text")
    usage.add_argument("--save", action="store_true", help="Write the result to the export folder.")
    usage.add_argument("--history", action="store_true", help="Save fetched rows to SQLite history.")

    all_usage = subparsers.add_parser("all-usage", help="Fetch usage rows for every phone number.")
    all_usage.add_argument("--format", choices=["text", "json", "csv"], default="csv")
    all_usage.add_argument("--save", action="store_true", help="Write the result to the export folder.")
    all_usage.add_argument("--history", action="store_true", help="Save fetched rows to SQLite history.")

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
