# Yettel flotta CLI

Internal CLI for fetching Yettel Online Ugyfelszolgalat `Forgalmi adatok` rows by phone number.

The tool logs in with your Yettel username/password, stores authenticated cookies locally, submits the ASP.NET WebForms phone-number selector on `Usage.aspx`, and parses the returned usage data into text, JSON, CSV, XLSX exports, or SQLite history.

Two portal layouts are supported. The parser first looks for the newer allowance list (`<ul id="Allowances">`), then falls back to the classic `Forgalmi adatok` table. If neither is present, the command fails with a layout error instead of returning empty data.

## Requirements

- Python 3.11 or newer
- No third-party runtime dependencies. HTTP, HTML parsing, SQLite, and the `.xlsx` writer are all built on the standard library. `pytest`, `ruff`, and `pre-commit` are dev-only extras.

## Security

Do not commit credentials or session data.

Ignored by git:

- `.env`
- `.yettel-cookies.txt`
- `exports/`
- `yettel-history.sqlite3`
- `debug-html/`
- `.venv/`

Cookie files are written with user-only permissions (`0600`). The app never prints credentials or cookies. Debug HTML, when enabled, redacts phone-like numbers and WebForms hidden state (`__VIEWSTATE`, `__EVENTVALIDATION`) before writing files.

## First Setup

```bash
cp .env.example .env
# edit .env and set YETTEL_USERNAME and YETTEL_PASSWORD
make refresh-venv
make precommit-install
```

`make refresh-venv` deletes and rebuilds `.venv`, then installs the project with local dev tools.
`make precommit-install` installs the git hook that runs format checks, lint, and tests before every commit.

## Recommended Start

```bash
make yettel
```

This will:

1. create or refresh `.venv` if needed
2. install the CLI and dev tools if needed
3. run Ruff lint
4. run all pytest tests
5. start the numbered menu only if checks pass

For a faster start without tests:

```bash
make run
```

## Menu

Running `make yettel`, `make run`, or `yettel` with no subcommand opens:

```text
1. Login and save session
2. Check saved session
3. List phone numbers
4. Fetch usage by phone number
5. Fetch usage by selecting a phone number
6. Fetch last selected phone again
7. Fetch all phone numbers and export
8. Build business report
9. Open exports folder
10. Exit
```

Notes:

- Options 4-6 ask for an output format, then offer export and SQLite history. Picking `xlsx` always writes a file, since it is not printable.
- Option 5 accepts either the full phone number or its list index, and supports a substring filter first.
- Option 8 uses the configured default format (`xlsx` unless `YETTEL_DEFAULT_FORMAT` says otherwise).
- `q`, `quit`, and `exit` work in place of `10`. Ctrl+C or Ctrl+D exits the menu cleanly with status `0`.

## Make Commands

```bash
make help
make install
make install-dev
make refresh-venv
make yettel
make run
make status
make login
make phones
make usage PHONE=201234567 FORMAT=json
make all-usage FORMAT=csv
make report REPORT_FORMAT=xlsx
make test
make lint
make format
make check
make precommit-install
make precommit-run
make precommit-uninstall
make clean
```

- `FORMAT` applies to `make usage` and `make all-usage`. It can be `text`, `json`, `csv`, or `xlsx`.
- `REPORT_FORMAT` applies to `make report` and defaults to `xlsx`.
- `make all-usage` always passes `--save`, so it writes an export file in addition to printing.
- `make install` installs the CLI only; `make install-dev` also installs the test/lint extras and is what every other target depends on.

## Direct CLI Commands

After `make refresh-venv`, either use the Makefile or run the installed command from the venv:

```bash
.venv/bin/yettel login
.venv/bin/yettel status --check-remote
.venv/bin/yettel phones
.venv/bin/yettel phones --format json
.venv/bin/yettel usage 201234567
.venv/bin/yettel usage 201234567 --format json
.venv/bin/yettel usage 201234567 --format csv
.venv/bin/yettel usage 201234567 --format csv --save --history
.venv/bin/yettel all-usage --format csv --save --history
.venv/bin/yettel report
.venv/bin/yettel report --open
```

Global options, valid before the subcommand:

```text
--env-file PATH      .env file to load. Default: .env
--cookie-file PATH   Override the saved cookie file path
--export-dir PATH    Override the export folder
--db-path PATH       Override the SQLite history database
```

Per-command flags:

```text
login       --username, --password        Fall back to YETTEL_USERNAME / YETTEL_PASSWORD, then an interactive prompt
status      --check-remote                Make a portal request to verify the session, not just the cookie file
phones      --format text|json
usage       --format, --save, --history, --open
all-usage   --format, --save, --history, --open
report      --format, --open
```

Default format per command when neither `--format` nor `YETTEL_DEFAULT_FORMAT` is set: `text` for `usage`, `csv` for `all-usage`, `xlsx` for `report`.

Exit codes: `0` on success, `1` on a handled Yettel error (login failure, expired session, unknown phone, layout change), `2` on argument errors, `130` when a subcommand prompt is interrupted with Ctrl+C.

If the portal redirects to the login page, run:

```bash
make login
```

## Output

Single-number usage returns rows with:

- `name`
- `limit`
- `available`
- `valid_until`

`text`, `json`, and `csv` print to stdout, and also write a file when `--save` is used. `xlsx` is file-only: it is written to the export folder whether or not `--save` is passed.

CSV output is Excel-friendly by default:

- UTF-8 with BOM
- comma-separated (`,`), matching Office Excel's normal `.csv` open behavior
- safe CSV quoting

CSV exports include business context columns:

- `phone`
- `fetched_at`
- `name`
- `limit`
- `available`
- `valid_until`

Exports are written to `exports/` by default, named `usage_<phone>_<timestamp>.<ext>` for a single number and `usage_all_<timestamp>.<ext>` for a full run.

SQLite history is stored in `yettel-history.sqlite3` when `--history` is used. The `report` command always saves a snapshot.

Native Excel (`.xlsx`) output is also supported. Workbooks include:

- `Summary`: one row per phone with key data/SMS fields and warning count
- `Usage`: all raw usage rows
- `Warnings`: low-data and expiry warnings
- `Changes`: differences versus the latest saved SQLite snapshot

The report command is the main business workflow:

```bash
make report
```

It fetches all phone numbers, compares them with the latest history snapshot, exports an `.xlsx` report, saves the new snapshot to SQLite, and prints warnings/changes in the terminal (first 10 of each, with a count of the rest).

Warnings come from two rules: available data at or below `YETTEL_LOW_DATA_GB_THRESHOLD`, and a validity date within `YETTEL_EXPIRY_WARNING_DAYS` (already expired is reported as `critical`).

Running `report` with `--format csv|json|text` still fetches, compares, saves history, and prints the summary, but those files contain the raw usage rows only. The `Summary`, `Warnings`, and `Changes` sheets exist in `xlsx` output only.

## Environment Variables

```env
YETTEL_USERNAME=your_username
YETTEL_PASSWORD=your_password

# Optional
YETTEL_COOKIE_FILE=/absolute/path/to/.yettel-cookies.txt
YETTEL_EXPORT_DIR=/absolute/path/to/exports
YETTEL_HISTORY_DB=/absolute/path/to/yettel-history.sqlite3
YETTEL_TIMEOUT_SECONDS=30
YETTEL_RETRIES=1
YETTEL_DEFAULT_FORMAT=xlsx
YETTEL_LOW_DATA_GB_THRESHOLD=5
YETTEL_EXPIRY_WARNING_DAYS=3
YETTEL_EXPORT_OPEN_AFTER_CREATE=false
YETTEL_DEBUG_HTML_DIR=/absolute/path/to/debug-html
```

Values already present in the real environment win over `.env`. An unrecognized `YETTEL_DEFAULT_FORMAT` is ignored rather than treated as an error.

If `YETTEL_DEBUG_HTML_DIR` is set and the parser cannot find phone numbers or usage rows, the app writes redacted HTML there and includes the debug file path in the error.

## Tests

```bash
make check
```

`make check` runs:

- Ruff lint
- pytest

Tests use sanitized HTML fixtures only. They do not call the live Yettel portal and do not need credentials.

Current coverage (20 tests):

- login form parsing
- WebForms hidden-field preservation and select-option handling
- phone dropdown parsing, including a selector that lives in a later form on the page
- usage table parsing (classic `Forgalmi adatok` table)
- usage parsing from the newer allowance list layout
- layout-change detection when neither layout is present
- phone-number normalization
- redaction of phones and WebForms state in debug HTML
- expired session detection
- mocked login POST fields
- mocked usage POST fields, including rejection of a phone missing from the dropdown
- CSV rendering with business context columns
- SQLite history persistence
- latest-history snapshot lookup
- business report change detection
- native `.xlsx` package generation
- config loading of business defaults
- menu exit behavior, including a clean Ctrl+C exit

## Pre-commit

Install the hook once:

```bash
make precommit-install
```

Run the same hooks manually:

```bash
make precommit-run
```

The hook runs:

- `ruff format --check .`
- `ruff check .`
- `pytest`

This means commits are blocked when formatting, lint, or tests fail. The hook uses `.venv/bin/python`, so run `make refresh-venv` first if the virtualenv is missing or stale.

## Project Layout

```text
src/yettel_cli/
  __main__.py   entry point behind the `yettel` script
  cli.py        argument parsing, menu, and command handling
  client.py     HTTP session, login, WebForms posts
  config.py     .env loading and path/threshold config
  constants.py  portal URLs and WebForms field names
  errors.py     user-facing error types
  models.py     typed data models
  output.py     text, JSON, CSV rendering and export helpers
  parsing.py    HTML form, table, and allowance-list parsers
  report.py     business summaries, warnings, changes
  storage.py    SQLite history
  xlsx.py       native Excel workbook writer

tests/
  test_client.py               login/usage POST behavior against mocked responses
  test_output_storage_cli.py   rendering, history, report, xlsx, config, menu
  test_parsing.py              form, table, allowance, redaction parsers
  fixtures/                    sanitized portal HTML samples
```
