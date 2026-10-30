# OneDrive Sorter

A single-page, browser-only app that sorts a personal OneDrive from a **reviewed move manifest**.
There is no backend, no API key and no AI call at run time. Your Microsoft token goes from Microsoft
straight into the page's memory (MSAL.js, OAuth 2.0 PKCE) and is never sent anywhere else.

> Governing principle: *Recovery First, Verification Second, Organization Third, Automation Last.*

## What it does

1. Loads a manifest CSV.
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

### 1. Register an Azure app (once)

1. Go to the Azure portal, **Microsoft Entra ID > App registrations > New registration**.
2. Supported account types: **Personal Microsoft accounts only**.
3. Redirect URI: platform **Single-page application (SPA)** and the exact URL you will open the page
   from (see step 2), including the trailing slash or file name.
4. After creating it, copy the **Application (client) ID**.
5. Under **API permissions**, add Microsoft Graph delegated permissions `Files.ReadWrite` and
   `User.Read`.

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

## Notes

- Sources are resolved by name from the OneDrive root. If the same name exists elsewhere, use a path
  in `SourceFile` to be explicit.
- The undo record uses the manifest columns, with an empty `DestinationFolder` meaning the OneDrive
  root. Empty destinations are rejected by the validator, so treat it as an audit record and restore
  root-level items by hand or edit the file first.
- The earlier proof of concept let Claude (via Puter.js) invent a plan from free text and could
  delete. That was removed on purpose: plans now come from a manifest a human has verified.
