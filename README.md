# Yettel flotta CLI

Internal CLI for fetching Yettel Online Ugyfelszolgalat `Forgalmi adatok` rows by phone number.

The tool logs in with your Yettel username/password, stores authenticated cookies locally, submits the ASP.NET WebForms phone-number selector on `Usage.aspx`, and parses the returned HTML table into text, JSON, CSV, exports, or SQLite history.

## Security

Do not commit credentials or session data.

Ignored by git:

- `.env`
- `.yettel-cookies.txt`
- `exports/`
- `yettel-history.sqlite3`
- `.venv/`

Cookie files are written with user-only permissions (`0600`). The app never prints credentials or cookies. Debug HTML, when enabled, redacts phone-like numbers and WebForms hidden state before writing files.

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

Running `make yettel`, `make run`, or `yettel` opens:

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

## Make Commands

```bash
make help
make refresh-venv
make yettel
make run
make status
make login
make phones
make usage PHONE=201234567 FORMAT=json
make all-usage FORMAT=csv
make report
make test
make lint
make format
make check
make precommit-install
make precommit-run
make precommit-uninstall
make clean
```

`FORMAT` can be `text`, `json`, `csv`, or `xlsx`.

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

Exports are written to `exports/` by default.

SQLite history is stored in `yettel-history.sqlite3` when `--history` is used.

Native Excel (`.xlsx`) output is also supported. Workbooks include:

- `Summary`: one row per phone with key data/SMS fields and warning count
- `Usage`: all raw usage rows
- `Warnings`: low-data and expiry warnings
- `Changes`: differences versus the latest saved SQLite snapshot

The report command is the main business workflow:

```bash
make report
```

It fetches all phone numbers, compares them with the latest history snapshot, exports an `.xlsx` report, saves the new snapshot to SQLite, and prints warnings/changes in the terminal.

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

If `YETTEL_DEBUG_HTML_DIR` is set and the parser cannot find usage rows, the app writes redacted HTML there and includes the debug file path in the error.

## Tests

```bash
make check
```

`make check` runs:

- Ruff lint
- pytest

Tests use sanitized HTML fixtures only. They do not call the live Yettel portal and do not need credentials.

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

Current coverage includes:

- login form parsing
- WebForms hidden-field preservation
- phone dropdown parsing
- usage table parsing
- expired session detection
- mocked login POST fields
- mocked usage POST fields
- CSV rendering
- SQLite history persistence
- latest-history snapshot lookup
- business report warnings and change detection
- native `.xlsx` package generation
- menu exit behavior

## Project Layout

```text
src/yettel_cli/
  cli.py        menu and command handling
  client.py     HTTP session, login, WebForms posts
  config.py     .env and path config
  constants.py  portal constants and field names
  errors.py     user-facing error types
  models.py     typed data models
  output.py     text, JSON, CSV, export helpers
  parsing.py    HTML form/table parsers
  report.py     business summaries, warnings, changes
  storage.py    SQLite history
  xlsx.py       native Excel workbook writer

tests/
  fixtures/     sanitized portal HTML samples
```
