# Testing guide

How OneDrive Sorter is tested, what each layer protects, and how to test it yourself on a real
OneDrive. Written so that a person or an AI tool can pick the project up cold.

## Run everything

```bash
pip install pytest "mcp>=2,<3"
python -m pytest -q                      # all Python tests (about half a minute)

npm install --no-save playwright@1.49.0  # once
npx playwright install chromium          # once
node tests/gui_smoke.js                  # the page in cloud mode, Microsoft mocked
node tests/gui_local.js                  # the page + the real backend, end to end
```

`python -m pytest --collect-only -q | tail -1` prints the current number of Python tests.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs all of this on every push and pull request:
the Python tests on Linux, Windows and macOS (Python 3.11 and 3.13), both browser tests, and a
clean install of the built package on all three operating systems.

## The layers and what they protect

| Layer | Files | Guards |
| --- | --- | --- |
| Rules and manifest | `tests/test_rules.py`, `tests/test_manifest.py` | Row validation messages; CSV quirks (BOM, quotes, blank lines, odd slashes); the page's copy of the rules equals `rules.json`; the root page equals the packaged page; the bundled guides equal their sources |
| Engine | `tests/test_engine.py`, `tests/test_cli.py` | **Never overwrite; never leave the root** (`..`, absolute paths, backslashes, drive letters, symlink escapes); two rows to one destination; destination appearing after the check; undo restores everything and refuses to overwrite; dry run is the default |
| Backend security | `tests/test_server.py` | Loopback only; token required; wrong `Host` or `Origin` refused; no cross-site (CORS) headers or preflight answers; body limits; one page and no other files served; the server re-checks instead of trusting the page; pause/resume/stop; undo log names validated |
| Proposals and context | `tests/test_proposals.py`, `tests/test_server.py`, `tests/test_mcp.py` | Proposal names validated; notes cleaned; context off by default; only plain text files directly inside the chosen folder; settings changes apply without a restart; an unusable folder is rejected and nothing is saved |
| MCP protocol | `tests/test_mcp.py`, `tests/test_claude_config.py` | The real server run with the real MCP client: exact tool list, **no tool that can move anything**, the sorted folder byte-for-byte unchanged after every tool is called, path escapes refused with a readable reason, hostile names neutralised, the project `.mcp.json` really starts the server, every tool named in the docs exists |
| Whole chain | `tests/test_end_to_end.py` | Claude proposes through MCP, a human loads, checks, executes and undoes through the API, and the folder is verified unchanged until the human steps |
| Browser | `tests/gui_smoke.js`, `tests/gui_local.js` | Cloud mode with mocked Microsoft; local mode against the real backend including a hostile proposal note rendered as text, the context checkbox and selector, execute, and undo |
| Clean install | `tests/package_smoke.py` (run by CI from outside the repo) | The built wheel carries `rules.json`, the page and the guides; the `onedrive-sorter` command, backend and MCP server all work from a fresh environment |

## When you change something

- **Rules:** edit `sorter/rules.json`, then update the `RULES` copy near the top of the script in
  `sorter/web/index.html` (cloud mode has no backend to ask), then `python tools/sync.py`. A test fails
  if the copies differ.
- **The page:** edit `sorter/web/index.html`, then `python tools/sync.py` (it copies to the root
  `index.html` that GitHub Pages serves).
- **README or these guides:** edit the files in `docs/` or the root `README.md`, then
  `python tools/sync.py` (it refreshes the copies bundled for AI tools in `sorter/context/`).
- **MCP tools:** adding or renaming one means updating `tests/test_mcp.py`, `tests/test_claude_config.py`,
  `tests/package_smoke.py` and `docs/CLAUDE_CODE.md`. Do not add a tool that moves, renames or deletes;
  the tests are written to fail if you do.

## Manual test on a real OneDrive (not covered by CI)

CI cannot sign in to a OneDrive or run Claude Code interactively. Do this once on your own machine,
with a throwaway folder first.

1. In your OneDrive folder create `Sorter Test` and put a few dummy files in it (a PDF, a folder). Wait
   until OneDrive shows them as synced.
2. Make a small manifest for those dummies (see `USAGE_FOR_AI.md`, section 5). Never test on real
   documents first.
3. Dry run: `onedrive-sorter check manifest.csv --root "<path to Sorter Test>"`. Expect `ready` for each
   good row and nothing changed on disk.
4. Start the page: `onedrive-sorter serve --root "<path to Sorter Test>"`, open the printed address, load the
   manifest, **Check**, then **Execute**. Confirm the files moved, the sync icons settle, and the same moves
   appear on onedrive.com.
5. **Undo last run**. Confirm everything returns, locally and on onedrive.com.
6. Conflict test: put a file with the same name in a destination, run again, and confirm that row is reported
   as `name conflict` and nothing is overwritten.
7. Claude Code: follow `docs/CLAUDE_CODE.md`; confirm `claude mcp list` shows the server connected, that the
   approval prompts appear as described, that `/mcp__onedrive-sorter__sort_folder` produces a proposal, and that
   nothing in the folder changes until you press Execute in the page.
8. Context files: tick the checkbox in the page, choose a location, ask Claude to call `list_context_files`,
   then untick it and confirm the next call reports it as off, without restarting anything.

Windows notes: use the folder shown by File Explorer for OneDrive (often `C:\Users\<you>\OneDrive`). Quote
paths that contain spaces. If `python` is not found use `py`.

## Known gaps

- No automated test signs in to a real Microsoft account, runs the OneDrive sync client, or drives a real
  Claude Code session. The manual steps above cover those.
- "Files On-Demand" placeholders (online-only files) are expected to move without downloading, but this has
  not been verified against a real sync client.
- Very large moves (thousands of files) have not been timed against OneDrive's sync.

## If a test fails

| Failure | Likely cause |
| --- | --- |
| "run: python tools/sync.py" | You edited the page, README or a guide without syncing the copies |
| Rules drift test | `rules.json` and the `RULES` copy in the page differ |
| MCP tool list test | A tool was added, renamed or removed; update the tests and docs listed above |
| Browser test cannot launch Chromium | Run `npx playwright install chromium` |
| `No module named mcp` | `pip install "mcp>=2,<3"` for the Python you run pytest with |
