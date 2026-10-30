# OneDrive Sorter

A single-page, browser-only app that sorts a personal OneDrive from a **reviewed move manifest**.
There is no backend, no API key and no AI call at run time. Your Microsoft token goes from Microsoft
straight into the page's memory (MSAL.js, OAuth 2.0 PKCE) and is never sent anywhere else.

> Governing principle: *Recovery First, Verification Second, Organization Third, Automation Last.*

## What it does

1. Loads a manifest CSV. (Either use the steps below, or see the rclone alternative if you do not want to register an app.)
2. Validates every row against the rules (below). Rows that fail are unchecked, with the reason shown.
3. **Check** (read-only): finds each source in OneDrive and reports `ready`, `already there`,
   `source not found` or `name conflict`. It also lists the destination folders that will be created.
4. **Execute**: for each `ready` row, creates any missing destination folders, then moves the item.
   Moves are paced by a delay slider (500-5000 ms) and can be paused and resumed. Throttling (HTTP
   429/503) is retried using `Retry-After`.
5. Failures are listed at the end (pass-and-report: successes are not repeated).
6. **Download undo record** writes a CSV of where every moved item came from.

It never deletes, overwrites or renames anything. If the destination already holds an item with the
same name, that row is reported as a conflict and skipped.

## Manifest format

CSV with these columns (extra columns are ignored):

| Column | Meaning |
| --- | --- |
| `SourceFile` | Name of an item in the OneDrive root, or a path relative to the root (`Folder/file.pdf`). Files and folders both work. |
| `DestinationFolder` | Target folder path relative to the root. Missing folders are created. |
| `Category`, `SubCategory`, `Notes` | Informational. |
| `Confidence` | Informational (shown in the table). |
| `Status` | Must be `Verified` to be selected by default. |
| `MoveAction` | Must be `MOVE`. |

Example:

```csv
SourceFile,DestinationFolder,Category,SubCategory,Confidence,Status,MoveAction,Notes
sf86r092817.pdf,Career/Security Clearance,Career,Security Clearance,100,Verified,MOVE,SF-86 questionnaire
```

## Rules enforced (Rules v37, consolidated)

These come from `CURRENT_RULES_v37_Consolidated.pdf`, the rule set from the Copilot candidate-set
test against a OneDrive file inventory. The longer v37 document in the Google Drive "AI Shared
Workspace" was used to sort Google Drive and is deliberately not applied here.

Top-level folders: `Academic`, `Career`, `Self-Paced Learning`, `Professional Training`,
`Administrative`, `Staging-Probable`, `Unsorted`.

Second-level folders, where the rules define them:

- **Academic:** University Coursework, Professional Training, Self-Paced Learning,
  Self-Directed Practice, Academic Support Material. Anything else (for example `ARIN 350`) is
  flagged for review.
- **Career:** Resume Workspace, Applications, Interviews, Employers, Security Clearance.
- **Professional Training:** Revature PET, Assessments, Coding Labs, Projects, Feedback.

A row is also held back when `MoveAction` is not `MOVE`, `Status` is not `Verified`, the source or
destination is empty, or the destination contains `.` / `..` segments. You can still tick a held-back
row to accept the exception.

## Setup

### 1. Register an app with your personal Microsoft account (once, free)

You do not need an Azure subscription, a credit card or a work/school (enterprise) account. The
registration is a one-minute form. (Portal menus change over time; the names below may differ slightly.)

1. Decide your redirect URI first, because you enter it during registration. It must exactly match the
   URL you open the page from (see step 2), for example `https://<user>.github.io/OneDrive-Sorter/` or
   `http://localhost:8080/`.
2. Sign in at <https://entra.microsoft.com> (or <https://portal.azure.com>) with the **same personal
   Microsoft account that owns the OneDrive** (outlook.com, hotmail.com, live.com, etc.). A personal
   account normally gets a "Default Directory" tenant automatically. If you are told you have no
   tenant or directory, see Troubleshooting below.
3. Go to **App registrations** (Entra: *Entra ID > App registrations*) and choose **New registration**.
4. Fill in the form:
   - **Name:** anything, for example `OneDrive Sorter`.
   - **Supported account types:** **Personal Microsoft accounts only**. (If that option is not shown,
     choose "Accounts in any organizational directory and personal Microsoft accounts".)
   - **Redirect URI:** platform **Single-page application (SPA)**, value from step 1. It must be the SPA
     platform, not "Web" or "Public client", or sign-in fails with a PKCE/CORS error.
5. Click **Register**. On the overview page, copy the **Application (client) ID**. You paste this into
   the app. There is no client secret to create.
6. Open **API permissions > Add a permission > Microsoft Graph > Delegated permissions** and add
   `Files.ReadWrite` and `User.Read`. For a personal account you do not need (and cannot use) admin
   consent; you approve the permissions yourself on first sign-in.
7. Optional: under **Authentication**, add a second SPA redirect URI so the same registration works both
   locally and on GitHub Pages.

Troubleshooting:

| Message | Fix |
| --- | --- |
| No tenant / "you don't have access to this directory" when opening App registrations | Sign up for a free Azure account with the same personal account at <https://azure.microsoft.com/free> (it may ask for phone or card verification, and you are not charged for the registration), then retry. |
| `AADSB90015` / "Cross-origin token redemption is permitted only for the Single-Page Application client-type" | The redirect URI was added under the wrong platform. Remove it and add it again under **Single-page application**. |
| `AADSTS50011` redirect URI mismatch | The page URL differs from the registered one (check `http` vs `https`, port, trailing slash, file name). |
| `AADSTS700016` / "application not found in the directory" | Account types are not set to allow personal accounts. Change them in **Authentication > Supported account types**. |
| `AADSTS65001` consent required | Sign in again and accept the permission prompt. |
| Popup blocked | Allow popups for the page. |

### 2. Serve the page

Microsoft sign-in does not work from a `file://` URL. Either:

**GitHub Pages:** enable Pages for this repository (Settings > Pages) and use
`https://<user>.github.io/OneDrive-Sorter/` as the redirect URI.

**Locally:**

```bash
python3 -m http.server 8080
```

then open `http://localhost:8080/` and register `http://localhost:8080/` as the redirect URI.

### 3. Use it

1. Paste your client ID (it is remembered in your browser) and click **Connect OneDrive**.
2. Choose the manifest CSV.
3. Click **Check**, read the table and the log, untick anything you do not want.
4. Click **Execute checked rows** and confirm.
5. Download the undo record when done.

## Alternative: rclone (no app registration)

If you would rather not register an Azure app, the app can export the selected rows as a bash script
for [rclone](https://rclone.org), which ships its own Microsoft client ID. This runs on your computer,
not in the browser, and does not need you to sign in to the page at all.

1. Install rclone and run `rclone config`: choose a new remote, name it `onedrive`, storage type
   `onedrive`, leave the client ID and secret blank, choose **Microsoft Cloud Global**, and sign in with
   your personal account when the browser opens. Pick the **OneDrive Personal** drive when asked.
2. Load the manifest in the page and optionally run no other step (Check needs sign-in, so skip it).
   Untick rows you do not want and click **Export rclone script**.
3. Dry run (default, changes nothing): `bash onedrive_sorter_rclone.sh onedrive`
4. Real run: `DRY=0 bash onedrive_sorter_rclone.sh onedrive`

The script has the same guarantees as the app: it only moves; it skips a row if the source is missing
or the destination name already exists; it creates missing folders; it waits between moves (the pacing
slider value at export time); and it appends every move to `undo_log_<timestamp>.tsv`, with a one-line
command in the script header to reverse them. If it cannot tell whether a path exists (for example a
network error), it reports an error and does not move that item.

## Notes

- Sources are resolved by name from the OneDrive root. If the same name exists elsewhere, use a path
  in `SourceFile` to be explicit.
- The undo record uses the manifest columns, with an empty `DestinationFolder` meaning the OneDrive
  root. Empty destinations are rejected by the validator, so treat it as an audit record and restore
  root-level items by hand or edit the file first.
- The earlier proof of concept let Claude (via Puter.js) invent a plan from free text and could
  delete. That was removed on purpose: plans now come from a manifest a human has verified.
