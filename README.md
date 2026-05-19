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
```

`make refresh-venv` deletes and rebuilds `.venv`, then installs the project with local dev tools.

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
6. Fetch all phone numbers and export
7. Exit
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
make test
make lint
make format
make check
make clean
```

`FORMAT` can be `text`, `json`, or `csv`.

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

CSV exports include business context columns:

- `phone`
- `fetched_at`
- `name`
- `limit`
- `available`
- `valid_until`

Exports are written to `exports/` by default.

SQLite history is stored in `yettel-history.sqlite3` when `--history` is used.

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
YETTEL_DEBUG_HTML_DIR=/absolute/path/to/debug-html
```

## Tests

```bash
make check
```

`make check` runs:

- Ruff lint
- pytest

Tests use sanitized HTML fixtures only. They do not call the live Yettel portal and do not need credentials.

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
  storage.py    SQLite history

tests/
  fixtures/     sanitized portal HTML samples
```
