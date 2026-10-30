# Test status and how to pick up (written 2026-10-30)

**Where we stopped:** the automated stages are finished. The project has reached the point where the only
remaining testing is **real-world testing** (a real OneDrive sync, a live Claude Code session, a Windows
run). By decision, testing is **paused here**. Nothing below has been tried against a real OneDrive yet.

## Where everything is

| What | Where |
| --- | --- |
| Pull request | https://github.com/EoUReDIt/OneDrive-Sorter/pull/2 (branch `claude/youthful-maxwell-8ci1wg` into `main`). Not merged. PR #1 (the original browser app) is merged. |
| Context guides for AI tools | Google Drive: AI Shared Workspace / "OneDrive Sorter (context files)" https://drive.google.com/drive/folders/1wRw8rXIFmOKM9yed2RRG8O6_dT6kbNK9 (guides are a snapshot of commit `411eb01`; a copy of this status file, `TEST_STATUS.md`, is in the same folder) |
| The same guides inside the app | `sorter/context/` (kept identical to `README.md`, `docs/TESTING.md`, `docs/USAGE_FOR_AI.md` by tests and `python tools/sync.py`) |
| How to test | `docs/TESTING.md` (layers, commands, and the manual real-world checklist) |
| How to connect Claude Code | `docs/CLAUDE_CODE.md` |
| How the pieces fit | `docs/ARCHITECTURE.md` |

## What has been tested, and the result

| Area | Result | Evidence |
| --- | --- | --- |
| Engine, manifest, rules, CLI | Pass | 129 Python tests passed locally on the last run (Linux sandbox, Python 3.13) |
| Local backend security (token, Host/Origin, no CORS, limits, re-check) | Pass | `tests/test_server.py`, real server on a random port |
| MCP server with the real MCP client over stdio | Pass | `tests/test_mcp.py`, `tests/test_claude_config.py`: exact tool list, no tool can move anything, folder unchanged after every tool |
| Context files (checkbox, selector, tools) | Pass | backend, MCP and browser tests, including a hostile context file and a hostile file name |
| Whole chain: Claude proposes, human loads, checks, executes, undoes | Pass | `tests/test_end_to_end.py` |
| Page in a real browser: cloud mode (Microsoft mocked) and local mode (real backend) | Pass | `tests/gui_smoke.js`, `tests/gui_local.js` (ran repeatedly, no flakes after two race fixes) |
| Clean install of the built package | Pass | `tests/package_smoke.py` locally, and in CI on Linux, Windows and macOS |
| GitHub Actions CI | Pass on `411eb01`: all 11 jobs (6 Python matrix jobs on 3 operating systems, 2 browser jobs, 3 clean-install jobs). Runs for the final commit `7293411` (runs 7 and 8) had just started when this was written and **were not checked**. |

Commits: `411eb01` was the last CI-verified commit. `7293411` added the empty/placeholder root fix. Anything
after that is documentation only.

## Problems found by testing (all fixed)

1. The page could stall waiting for Microsoft's script when offline. It is now loaded only in cloud mode.
2. Pasting a new link with a token into an already-open tab did not switch to local mode (browsers treat a
   hash change as the same page). The page now listens for the change.
3. Choosing "Another folder" in the context selector tried to save an empty path and showed an error before
   you could type. It now asks for a path first.
4. **An empty `--root` silently meant the current folder.** Now refused: "No folder given".
5. **An unset `ONEDRIVE_SORT_ROOT` reached the MCP server as the literal text `${ONEDRIVE_SORT_ROOT}`** and Claude
   Code showed only "Connection closed". This was seen in a real Claude Code session (the project `.mcp.json`
   was auto-detected with the variable unset). The server now says exactly what is wrong and what to set.
6. Test-only mistakes (a race when reading a file, an over-strict assertion) were fixed in the tests.

## Real-world testing still to do (nothing here is done)

Order matters: each step assumes the one before it passed. Use a throwaway `Sorter Test` folder inside OneDrive
first; only then the real folder. Tick these off as you go.

- [ ] **0. Prerequisites:** Python 3.11+, the OneDrive sync app signed in and fully synced, the project installed
  (`python -m pip install ".[mcp]"` in the project folder, `py -m pip` on Windows if `python` is not found).
  `onedrive-sorter --help` works.
- [ ] **1. Dry run:** `onedrive-sorter check manifest.csv --root "<Sorter Test path>"`. Expect `ready` rows and nothing changed.
- [ ] **2. Page, local mode:** `onedrive-sorter serve --root "<Sorter Test path>"`, open the printed address, load the
  manifest, **Check**, **Execute**. Confirm files moved locally, sync icons settle, and the same moves appear on onedrive.com.
- [ ] **3. Undo:** **Undo last run**. Confirm everything returns, locally and on onedrive.com.
- [ ] **4. Conflict:** same name already in a destination. Expect `name conflict`, nothing overwritten.
- [ ] **5. Online-only files (Files On-Demand):** move one placeholder. Expect it moves without downloading. *Unverified assumption.*
- [ ] **6. Claude Code connection:** `claude mcp add onedrive-sorter -- onedrive-sorter mcp --root "<Sorter Test path>"`,
  then `claude mcp list` shows connected; approval prompts appear as `docs/CLAUDE_CODE.md` describes. Also retest the
  `.mcp.json` way with `ONEDRIVE_SORT_ROOT` set (and once unset, to see the new message).
- [ ] **7. Claude proposes:** `/mcp__onedrive-sorter__sort_folder`. Confirm a proposal appears under "Proposals from Claude",
  and **nothing** in the folder changes until you press Execute.
- [ ] **8. Context files:** tick the checkbox, choose built-in guides, ask Claude for `list_context_files`; choose the
  Drive-synced folder; untick and confirm the next call reports it off, with no restart.
- [ ] **9. Windows run:** repeat 0 to 3 on Windows with a path containing spaces. Note anything that differs.
- [ ] **10. A bigger batch:** a few hundred items, with the pacing slider; watch OneDrive's sync for errors or throttling.
- [ ] **11. Go live:** the real OneDrive folder with a small plan first.

For each step note: what you did, what you expected, what happened, and any messages. Bring failures back
along with the undo log (`~/.onedrive-sorter/logs/`) and the exact error text.

## Known risks and unverified assumptions

- OneDrive's reaction to many quick moves (throttling, sync conflicts) is unmeasured. Keep the pacing delay.
- The OneDrive folder path differs by account and OS (`OneDriveConsumer` on Windows personal accounts,
  `~/Library/CloudStorage/OneDrive-Personal` on a Mac); the README says "usually".
- Claude Code's exact prompt wording may differ from `docs/CLAUDE_CODE.md` (written from its documentation, not from
  a full interactive run).
- The MCP package is pinned to `mcp>=2,<3`; a new major version could change its API.
- On Linux there is no official OneDrive sync client, so local mode there needs the community client or an rclone mount.
- If the context folder sits inside the sorted folder, a plan could move the guides. The page warns but does not block.
- The Microsoft cloud mode has never been run against a real Microsoft account (Azure app not registered, GitHub Pages not enabled).

## If something goes wrong during real testing

1. Stop: press **Pause** or **Stop** in the page, or close the terminal running `serve`.
2. Undo: **Undo last run** in the page, or `onedrive-sorter undo ~/.onedrive-sorter/logs/moves_<timestamp>.jsonl --root "<folder>"`.
   Nothing is ever deleted or overwritten, so every move can be reversed unless you changed the destination afterwards.
3. Do not hand-delete the log; it is the only record of where things came from.

## Open decisions

- Merge PR #2 after the real-world tests (or earlier, if you want the work on `main`).
- Build a prompting launcher (auto-detect the OneDrive folder, confirm, remember it): recommended next step for non-technical users.
- Portable zip, or a single-file executable, if this is going to other people.
- Whether to enable GitHub Pages and register an Azure app for cloud mode at all.

## How to resume

1. Open this file and `docs/TESTING.md` (manual checklist) in the repository, or the Drive context folder.
2. Tell your AI tool: "Read docs/TEST_STATUS.md and docs/USAGE_FOR_AI.md, then help me with real-world test step N."
3. To re-run the automated suite before changing anything: `python -m pytest -q`, then `node tests/gui_smoke.js` and
   `node tests/gui_local.js` (see `docs/TESTING.md` for one-time setup).
4. After editing the page, README or guides: `python tools/sync.py`.
