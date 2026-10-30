# OneDrive Sorter

Sorts a personal OneDrive from a **reviewed move manifest**: a CSV that says "move this item to that
folder". Nothing moves until a person checks the plan and presses Execute, nothing is ever deleted or
overwritten, and every run can be undone.

It works in two ways:

- **Local mode (recommended):** a small program on your computer sorts your OneDrive *folder* and the
  OneDrive sync app carries the changes to the cloud. No Azure app registration and no tokens. Claude
  can help (using your own Claude login, no API key) by *proposing* plans through an MCP server that
  physically cannot move files.
- **Cloud mode:** the browser page signs in to Microsoft and moves files through the Graph API. It needs
  a free Azure app registration and has no Claude integration.

> **Quick setup is at the bottom of this file**, followed by the deployment options.

> Governing principle: *Recovery First, Verification Second, Organization Third, Automation Last.*

## What it does

1. Loads a manifest CSV (or, in local mode, a plan Claude proposed).
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

## Cloud mode setup (Azure app registration)

Only needed for cloud mode. Local mode needs none of this.

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

## Local mode (recommended)

Sort the OneDrive folder on your own computer and let the OneDrive sync app carry the changes to the
cloud. No Azure app registration is needed, and Claude can help through the MCP server
([docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md)). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the
pieces fit together and what each stage tested.

```bash
onedrive-sorter check my_manifest.csv --root "C:\Users\you\OneDrive"
onedrive-sorter run my_manifest.csv --root "C:\Users\you\OneDrive"            # dry run
onedrive-sorter run my_manifest.csv --root "C:\Users\you\OneDrive" --apply    # really move
onedrive-sorter undo ~/.onedrive-sorter/logs/moves_<timestamp>.jsonl --root "C:\Users\you\OneDrive"
```

(From an unpacked copy of the project without installing, `python -m sorter` does the same thing.)

Or use the browser page with the local backend (recommended):

```bash
onedrive-sorter serve --root "C:\Users\you\OneDrive"
```

Open the address it prints. Pacing, pause/resume, check, execute and undo all work from the page.

### Claude and other AI tools

`onedrive-sorter mcp --root <folder>` is an MCP server that Claude Code starts for you
([docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md)). Claude can read the rules, look at names, types, sizes and
dates, dry-run a draft and *propose* a plan. It has no tool that can move anything; you load the proposal in
the page (**Proposals from Claude**), check it, and press Execute yourself.

### Context files for AI tools (optional)

Guides and notes that outlive any one chat. In the page there is a card **Context files for AI tools** with a
checkbox ("There are context files") and a location selector:

- **Built-in guides:** this README, [docs/TESTING.md](docs/TESTING.md) and
  [docs/USAGE_FOR_AI.md](docs/USAGE_FOR_AI.md), shipped inside the app.
- **Another folder on this computer:** your own notes, for example a copy of those guides kept in a shared
  AI workspace folder. Only plain text files (`.md`, `.txt`, `.csv`, `.json`) directly inside it are shared.

They are **advisory only**: they never override what you or Claude decide, the folder rules, or the safety
limits, and the tools hand them over labelled as reference material, not instructions. Off by default;
the setting is stored in `~/.onedrive-sorter/config.json`; the MCP server re-reads it on every call, so turning
it on or off applies at once without restarting Claude Code. If you choose a folder inside the folder being
sorted, the page warns you so you do not accidentally include the guides in a plan.

Same guarantees as the browser app: moves only, never overwrites, anything outside the root is
refused, rows that fail the rules are held back unless you pass `--include-flagged`, and every move is
logged so it can be undone. Run the tests with `python -m pytest`.

## Notes

- Sources are resolved by name from the OneDrive root. If the same name exists elsewhere, use a path
  in `SourceFile` to be explicit.
- The undo record uses the manifest columns, with an empty `DestinationFolder` meaning the OneDrive
  root. Empty destinations are rejected by the validator, so treat it as an audit record and restore
  root-level items by hand or edit the file first.
- The earlier proof of concept let Claude (via Puter.js) invent a plan from free text and could
  delete. That was removed on purpose: plans now come from a manifest a human has verified.

## Hosting on GitHub Pages (walkthrough)

The app is a single static `index.html`, so GitHub Pages can host it with no build step. The live URL
for this repository will be `https://eouredit.github.io/OneDrive-Sorter/` (owner name in lowercase).

1. **Get `index.html` onto the branch Pages will publish.** Pages publishes from one branch. Merge the
   work on `claude/youthful-maxwell-8ci1wg` into your default branch (usually `main`), for example
   with a pull request. `index.html` must be at the repository root, where it is now.
2. **Turn on Pages.** In the repository on GitHub, open **Settings > Pages**. Under **Build and
   deployment**, set **Source** to **Deploy from a branch**, choose your default branch and the
   **/ (root)** folder, then **Save**.
3. **Wait for the first deployment.** It usually takes one to two minutes. The Pages settings screen
   shows "Your site is live at ..." when it is ready, and the **Actions** tab shows the deployment run.
4. **Register that exact URL as the redirect URI.** In your Azure app registration, open
   **Authentication**, and under **Single-page application** add
   `https://eouredit.github.io/OneDrive-Sorter/` (with the trailing slash). Keep
   `http://localhost:8080/` as a second URI if you also want to test locally. Save.
5. **Open the site, paste your client ID, and click Connect OneDrive.** Then follow "Use it" above.
   If you see `AADSTS50011` (redirect URI mismatch), compare the address bar to the registered URI
   character by character.
6. **Updating later.** Push changes to the published branch; Pages redeploys on its own. Hard-refresh
   the page (Ctrl+Shift+R) if you still see the old version.

Things to know:

- **Nothing private is hosted.** Pages serves only `index.html` and this README's repository files.
  Your manifest is loaded from your own disk by the browser and never uploaded, and `*.csv` is in
  `.gitignore` so it cannot be committed by accident. Your Azure client ID is not a secret.
- **The site is public.** Anyone with the link can open the page, but they cannot do anything without
  signing in to their own OneDrive. GitHub Pages sites are public on most plans even when the repository
  is private, and Pages from a private repository may require a paid GitHub plan. Check
  **Settings > Pages** for what your plan allows.
- **Alternatives to Pages.** Any static host works the same way, as long as the redirect URI you
  register matches the page URL. For local use, `python3 -m http.server 8080` is enough.

## Quick setup

Local mode with Claude, about ten minutes. Practise on a throwaway folder first.

1. **You need:** Python 3.11 or newer (on Windows tick "Add python.exe to PATH" in the installer), the
   OneDrive sync app signed in and **fully synced**, and, optionally, Claude Code signed in.
2. **Get the project:** on GitHub choose *Code > Download ZIP* and extract it anywhere (where you extract it
   does not matter), or `git clone` it. Open a terminal inside the extracted folder.
3. **Install:**
   ```bash
   python -m pip install ".[mcp]"
   ```
   On Windows use `py -m pip install ".[mcp]"` if `python` is not found. This adds the `onedrive-sorter`
   command. (A virtual environment or `pipx` keeps it tidy if you prefer.)
4. **Find your OneDrive folder.** Open it in File Explorer or Finder and copy the path. Usually
   `C:\Users\<you>\OneDrive` on Windows (PowerShell: `$env:OneDriveConsumer` for a personal account), or
   `~/Library/CloudStorage/OneDrive-Personal` on a Mac.
5. **Practise safely.** Inside OneDrive make a folder `Sorter Test` with a couple of dummy files, and a
   manifest for them (see [Manifest format](#manifest-format)). Then a dry run, which changes nothing:
   ```bash
   onedrive-sorter check manifest.csv --root "C:\Users\<you>\OneDrive\Sorter Test"
   ```
6. **Open the page:**
   ```bash
   onedrive-sorter serve --root "C:\Users\<you>\OneDrive\Sorter Test"
   ```
   Open the address it prints (it contains a one-time token). Load the manifest, press **Check**, read the
   table, press **Execute**, then try **Undo last run**.
7. **Connect Claude (optional):** in the project folder run
   ```bash
   claude mcp add onedrive-sorter -- onedrive-sorter mcp --root "C:\Users\<you>\OneDrive\Sorter Test"
   ```
   `claude mcp list` should show it connected. In Claude Code type `/mcp__onedrive-sorter__sort_folder`, approve
   the tool prompts, then load Claude's plan under **Proposals from Claude** in the page. Details and
   troubleshooting: [docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md).
8. **Context files (optional):** in the page tick *There are context files* and pick the built-in guides or
   your own folder. Ask Claude to read them (`list_context_files`).
9. **Go live:** repeat steps 6 and 7 with `--root` pointing at your real OneDrive folder, starting with a
   small plan. Everything is logged, so **Undo last run** reverses a mistake.

## Ways to deploy

Which to pick depends on who will use it. Options 1 and 4 exist today; 2 and 3 are recommended next steps
and are not built yet.

| # | Way | Best for | Good | Watch out for | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | **Install with pip or pipx** from the project (`pip install ".[mcp]"`, or from GitHub once the repository is public or you are signed in) | You, or anyone comfortable with a terminal | One command; easy updates; the built package is tested on Windows, macOS and Linux on every push | Needs Python | Built and CI-tested |
| 2 | **Portable zip with a launcher** (`start.bat` for Windows, `start.command` for Mac): extract, double-click, it finds Python, installs, asks which folder, and opens the page | People who do not use a terminal | No install knowledge needed; extract location does not matter | Still needs Python unless it is bundled; a launcher script per OS to maintain | Recommended; not built |
| 3 | **Single-file executable** built by a GitHub Actions release workflow (PyInstaller): download one `.exe` or app | The widest audience | No Python needed | Large file; Windows SmartScreen and macOS Gatekeeper warnings without code signing; one build per OS | Recommended; not built |
| 4 | **Static page on GitHub Pages (cloud mode)**: the page signs in to Microsoft ([walkthrough](#hosting-on-github-pages-walkthrough)) | People who cannot install anything | Nothing to install | Needs an Azure app registration; no local backend, no Claude integration; the Pages site is public | Built |

My recommendation: option 1 now (it is what the CI proves works), then option 2 for non-technical users, and
option 3 only if you need to hand it to people without Python.

### Should it prompt for the folder?

Yes, but the **launcher** should ask, not the web page, and the install or extract location is irrelevant.

- The folder that gets sorted is a safety decision, so it is fixed when the program starts and the page can never
  change it (this is what stops a web page or an AI from steering the program at another folder).
- A good launcher would: look for your OneDrive folder automatically (Windows exposes it through
  `OneDriveConsumer`/`OneDrive` environment variables; on a Mac it is under `~/Library/CloudStorage`), show what
  it found and ask you to confirm, fall back to a native folder picker (or a typed path), remember the answer
  in a small settings file, and warn if the folder is not fully synced or not inside OneDrive.
- Then it starts `onedrive-sorter serve --root <the confirmed folder>`.

Today you pass `--root` yourself. A prompting launcher is not built yet; it is the natural first piece of
option 2 and a small job.

