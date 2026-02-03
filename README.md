# ChangePasswordIG

Automation tool to reset Instagram passwords via GMX mail.

## Flow Overview
- Load Instagram cookies from JSON.
- Log in to GMX mail.
- Find Instagram reset mail.
- Open reset link and enter new password.
- Verify the "password changed" mail.

## Environment Setup
Requirements:
- Python 3.10+
- Google Chrome
- Packages: `selenium`, `undetected-chromedriver`

Install dependencies:
```bash
pip install -r requirements.txt
```

Tip (if chromedriver download fails):
- Try again or ensure a stable network connection.

## Required Config
- Instagram cookie file path is set in `main.py` (`IG_COOKIE_PATH`).
- Input file: `input.txt` (tab-separated).

Input format (8 columns):
```
UID add	MAIL LK IG	USER	PASS IG	2FA	PHOI GOC	PASS MAIL	MAIL KHOI PHUC
aufiei	aufiei@gmx.de	zjsigjywkg	eaaqork1S		virtualcultural2@gmx.de	eaaqork1S	virtualcultural2@teml.net
```

Column meanings:
- `MAIL LK IG`: GMX email login
- `PASS MAIL`: GMX password (also used as the new IG password)
- `PASS IG`: if empty, GUI will copy from `PASS MAIL`
- `USER`: updated from mail subject if found

## Run CLI
1. Put data into `input.txt`.
2. Run:
```bash
python main.py
```
3. Output is written to `output.txt`.

## Run GUI
```bash
python gui.py
```

### GUI Components
Input:
- Browse/Load: select input file and load table.
- Paste Data: quick paste tab-separated data.

Config:
- Threads: number of parallel workers.
- Headless: toggle browser UI.
- Delete Selected/All: remove rows.

Table:
- 8 input columns, last column `NOTE` stores status.

Control:
- START: runs only rows not marked "Success".
- STOP: stops after the current row finishes.
- Progress/Success/Status: runtime counters.
- Export Success/All: save to txt file.

Notes:
- GUI auto-fills `PASS IG` from `PASS MAIL` when empty.
- Re-runs skip rows marked "Success".

## Status and Error Codes
CLI output (`output.txt` -> STATUS column):
- `SUCCESS`: all steps completed.
- `FAIL`: a step failed; check MESSAGE for details (e.g. `Cookie load failed`, `Step 1 Fail`, `Step 2 Fail`, `Step 3 Fail`, `Step 4 Fail`).
- `CRASH`: unhandled exception; check MESSAGE.

GUI NOTE column:
- `Success`: completed.
- `Pending`, `Running`: in progress.
- `Error: missing mail login/pass`: input row is missing required fields.
- `Error: <message>`: runtime error; usually matches the CLI MESSAGE.
- `Step1: open Instagram`, `Step1: login GMX`, `Step2: read mail`, `Step3: reset password`, `Step4: verify mail`: progress markers.

## Test Tips
1. Start with 1 row and `Threads=1`, headless off.
2. Confirm GMX login and mail open works.
3. Increase threads after a successful single run.

## Notes
- Instagram cookie path is in `main.py` (`IG_COOKIE_PATH`).
- If GMX UI changes, update selectors in `step2_get_link.py` or `mail_handler.py`.
