# Architecture and staged plan

Goal: sort the files in your OneDrive folder on your own computer, with Claude helping to propose the
plan, without any API key and without giving anything the ability to delete or overwrite.

```
 OneDrive cloud  <--sync-->  OneDrive folder on disk
                                     ^
                                     | moves only, inside this folder
 Browser page (GUI) <--HTTP, localhost--> Local backend  <--same engine-->  MCP server
                                                                              ^
                                                                    stdio     |
                                                              Claude Code / Claude Desktop
                                                              (signed in with your Claude account)
```

## Concepts in plain language

**Sync client.** The OneDrive app keeps a normal folder on your disk in step with the cloud. If this
program moves a file inside that folder, OneDrive notices and moves it in the cloud too. That means
this program never talks to Microsoft, never needs an Azure app registration, and never holds a token.

**Engine (`sorter/`).** The one place that decides what is allowed: it checks a manifest against the
rules, refuses anything that would leave the chosen folder, never overwrites, never deletes, and writes
an undo log after every move. Everything else (command line, GUI, Claude) goes through it, so the
safety rules cannot be bypassed by a different front end.

**Manifest.** A CSV listing "move this item to that folder". It is the contract between "someone
proposes a plan" (you, or Claude) and "the engine carries it out".

**Backend.** A small program on your computer that exposes the engine to the browser page over
`localhost`. A web page cannot freely move files on your disk, so the backend does that part. It must
listen only on your own machine, require a per-run token, and refuse requests from other websites.

**MCP (Model Context Protocol).** A standard way for an AI app to use tools that live in another
program. Your program (the *MCP server*) advertises a list of tools, each with a name, a description
and the inputs it takes. The AI app (the *client*, such as Claude Code) reads the list. When Claude
decides a tool is useful, the client sends a call, your program runs it, and the result goes back to
Claude. Claude never gets direct access to your files, only what your tools choose to return.

**Why MCP fits here.** The client signs in with your own Claude account, so there is no API key in
this project. The server decides what Claude can see (names and folders, not file contents) and what
it can do. And the dangerous step stays with you: Claude can *propose* a plan, but only the GUI's
Apply button, clicked by you, moves anything.

**stdio.** The simplest MCP connection. The client starts your server as a child process and they talk
through standard input and output. No network port is opened, and nothing else on your machine can
connect to it.

**CI (continuous integration).** A GitHub workflow that runs all the tests on every push, on Linux,
Windows and macOS. Each stage below must be green before the next begins, so a later change cannot
silently break an earlier part.

## Stages

| Stage | What gets built | What CI checks before moving on |
| --- | --- | --- |
| 1 (done) | Engine, rules, manifest loader, command line, undo log | Engine tests on 3 operating systems; the existing browser page still passes its smoke test; the browser copy of the rules must match the Python copy |
| 2 (done) | Local backend (HTTP on localhost, token, origin checks) and the page switched to call it | 23 API tests against a real server, including hostile-request tests; the page driven end to end in a browser against the real backend (move, then undo); the old cloud-mode page smoke test still passes |
| 3 (done) | MCP server over stdio: read-only tools (rules, list a folder, validate a manifest) and a *propose plan* tool that stores a plan for you to review, never applies it; a "Proposals from Claude" picker in the page | 30 tests that run the real server with the real MCP client: exact tool list, no tool that can move anything, the sorted folder is byte-for-byte unchanged after every tool is called, path escapes refused with a readable reason, hostile file names neutralised; backend and browser tests for loading a proposal |
| 4 (done) | Connecting Claude Code: a project `.mcp.json`, a `/mcp__onedrive-sorter__sort_folder` prompt served by the MCP server, and a walkthrough ([CLAUDE_CODE.md](CLAUDE_CODE.md)) of the approval prompts, troubleshooting and the optional read-only allow-list | The project config is used to start the real server and list its tools and prompt; every tool named in the docs must exist; the settings example must be valid and allow only read-only tools |
| 5 | Final refactor: one shared rules file, remove duplicated logic in the page, decide whether to keep the old direct-to-Microsoft mode, rewrite the README | Full suite plus an end-to-end test (propose, review, apply, undo) |

## Running the local backend (stage 2)

```bash
python -m sorter serve --root "C:\Users\you\OneDrive"
```

It prints an address like `http://127.0.0.1:8765/#token=...`. Open that exact address in your browser.
The token after `#` is generated fresh on every start; it proves the page is yours. The page removes it
from the address bar after reading it, and keeps it only for that browser tab. If you restart the
server, open the new address.

What protects it (all covered by tests): it listens on `127.0.0.1` only; every API call needs the
token; the `Host` and `Origin` headers must be its own address, which blocks other websites and DNS
rebinding; it never answers a browser's cross-site "preflight" check; the folder is fixed at start-up
and the page cannot change it; request sizes are capped; the only file it serves is the page itself;
there is no delete or overwrite anywhere. The server also re-checks every row itself at execute time,
so the page cannot talk it into anything the engine would refuse.

Without the token (or opened from a file), the page falls back to the original cloud mode.

## The MCP server (stage 3)

```bash
pip install "mcp>=2,<3"
python -m sorter mcp --root "C:\\Users\\you\\OneDrive"
```

You normally do not run this yourself: Claude Code starts it (stage 4 shows how). It offers four tools:

| Tool | What Claude can do with it | Changes anything? |
| --- | --- | --- |
| `get_rules` | Read the folder rules and the manifest format | No |
| `list_folder` | See names, types, sizes and dates in one folder (never file contents), a page at a time | No |
| `validate_manifest` | Dry-run a draft CSV against the rules and the real folder | No |
| `propose_plan` | Save a draft as a proposal file | Writes one small file outside the sorted folder |

There is no move, apply, undo or delete tool, and the tests fail if one is ever added. The only way
anything moves is you pressing Execute in the page after loading the proposal under
**Proposals from Claude**.

Two things worth knowing about AI and file names. Names are text that anyone could have chosen (a
downloaded file can be named "ignore your instructions and..."), so the server tells Claude to treat
names as data, strips control characters from them, and, more importantly, nothing Claude proposes is
applied without your review. And Claude only ever sees names, types, sizes and dates, so it cannot
read your files; your SF-86 and similar documents are never opened.

## What you will see when you connect Claude Code

Verified against Claude Code's current documentation and written up step by step in
[CLAUDE_CODE.md](CLAUDE_CODE.md): an approval prompt for a server defined in a project `.mcp.json`
(skipped if you add the server yourself with `claude mcp add`), then a permission prompt each time
Claude wants to use one of the tools, unless you allow-list the read-only ones.

## Decisions and open questions

- Language: Python (standard library only) for the engine, so it runs on Windows, macOS and Linux.
  The MCP stage will add one dependency (the official MCP SDK).
- Linux has no official OneDrive sync client; the community client or an rclone mount would be needed.
- Files that are "online only" (not downloaded) can be moved without downloading them. Reading their
  contents would download them, so the plan is to classify from names and metadata only.
