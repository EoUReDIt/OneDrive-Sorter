# Connecting Claude Code (stage 4)

This is the part where Claude gets to help, using your own Claude login (no API key). Claude Code
starts the sorter's MCP server on your computer and talks to it. Claude can look at names and propose a
plan; you review and apply it in the page.

## Before you start

1. Python 3.11 or newer, and the MCP package: `pip install "mcp>=2,<3"`
2. Claude Code installed and signed in (`claude` works in a terminal).
3. This project downloaded, with your terminal opened **in the project folder** (the one with `sorter/`).

## Connect it (two ways; pick one)

### A. One command (simplest, private to you)

```bash
claude mcp add onedrive-sorter -- python -m sorter mcp --root "C:\Users\you\OneDrive"
```

Use `python3` instead of `python` on macOS/Linux if `python` is not found. Everything after the `--`
is the command Claude Code will run; the `--` stops Claude Code from reading the sorter's own options
as its own. This is "local scope": it is stored in your Claude Code settings for this project and is not
shared with anyone.

### B. The project file `.mcp.json` (already in this repository)

It tells Claude Code how to start the server, and takes the folder from an environment variable so no
personal path is committed:

```bash
# macOS / Linux
export ONEDRIVE_SORT_ROOT="$HOME/OneDrive"
# Windows PowerShell
$env:ONEDRIVE_SORT_ROOT = "$HOME\OneDrive"
```

Set it, then start `claude` from the project folder in that same terminal.

## What you will be asked (in order)

1. **Approve the server (only for way B).** The first time Claude Code sees a server defined in a
   project `.mcp.json`, it asks you to approve it before using it. Until you do, `claude mcp list`
   shows it as pending approval. Way A skips this, because you added the server yourself. To be asked
   again later: `claude mcp reset-project-choices`.
2. **Approve tool calls.** The first time Claude wants to use one of the tools, Claude Code asks for
   permission and shows which tool and with what inputs. Read what it shows; the inputs are exactly
   what the server will receive. The exact wording of the choices (allow once, allow and don't ask
   again, deny) can differ between versions.

## Check that it works

In a terminal: `claude mcp list` should show `onedrive-sorter` as connected. Inside Claude Code,
`/mcp` opens the same status panel, with the number of tools (there should be six).

If it shows `Failed to connect`, `claude mcp get onedrive-sorter` explains why. Common causes:

| Symptom | Fix |
| --- | --- |
| `python` not found | Use `python3` (macOS/Linux) or `py` (Windows), or the full path to the interpreter you installed `mcp` into |
| `No module named mcp` | `pip install "mcp>=2,<3"` for the **same** Python the command uses |
| `No module named sorter` | Start `claude` from the project folder (or `pip install -e .` once) |
| Root is not a folder | Fix the path; quote it if it has spaces |
| `Connection closed` right after starting (way B) | `ONEDRIVE_SORT_ROOT` is not set in the terminal you started `claude` from, so the server received the literal text `${ONEDRIVE_SORT_ROOT}` and exited. Set it and restart `claude` |
| Way B: missing environment variable | Set `ONEDRIVE_SORT_ROOT` in the terminal you start `claude` from |

## Use it

Type `/mcp__onedrive-sorter__sort_folder` (Claude Code also lists it as `/onedrive-sorter:sort_folder`
when you type `/`), optionally followed by a focus such as `career documents`. That starts the
workflow the server describes: read the rules, look around, draft a manifest, validate it, and propose it.
Or just ask in your own words, for example "sort the top level of my OneDrive into the Career and
Academic folders and propose a plan".

Then, in a second terminal: `python -m sorter serve --root "C:\Users\you\OneDrive"`, open the address
it prints, choose the plan under **Proposals from Claude**, press **Load proposal**, then **Check**,
read the table, and **Execute** only if you are happy.

## Optional: stop being asked for the read-only tools

The five read-only tools are safe to pre-approve. Put this in `.claude/settings.json` (or
`.claude/settings.local.json` to keep it to yourself):

```json
{
  "permissions": {
    "allow": [
      "mcp__onedrive-sorter__get_rules",
      "mcp__onedrive-sorter__list_folder",
      "mcp__onedrive-sorter__validate_manifest",
      "mcp__onedrive-sorter__list_context_files",
      "mcp__onedrive-sorter__read_context_file"
    ]
  }
}
```

Leave `mcp__onedrive-sorter__propose_plan` out so you are still asked before a plan is saved. Rule
names have the form `mcp__<server>__<tool>`; `mcp__onedrive-sorter__*` would allow all six.

## What this connection can and cannot do

- Claude sees names, types, sizes and dates, one folder at a time. It cannot read file contents.
- The only thing it can write is a proposal file outside your OneDrive folder.
- There is no tool that moves, renames, overwrites or deletes anything. A test fails if one is added.
- Nothing is applied until you press Execute in the page; that step re-checks every row again.
- Anyone who can put a file in the folder can choose its name. The server tells Claude to treat names
  as data, but the real protection is that you review the plan before it is applied.
