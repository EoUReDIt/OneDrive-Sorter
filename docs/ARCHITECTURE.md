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
| 2 | Local backend (HTTP on localhost, token, origin checks) and the page switched to call it | API tests against a real server; page smoke test running against the backend; request-rejection tests |
| 3 | MCP server over stdio: read-only tools (rules, list a folder, validate a manifest) and a *propose plan* tool that stores a pending plan, never applies it | Protocol test: start the server, list tools, call each one; confirm there is no tool that moves anything |
| 4 | Connecting Claude Code: a project config file, a walkthrough of the prompts you will see, and a checklist to try it end to end | Config file parses; server starts from the config; tools listed match the documented ones |
| 5 | Final refactor: one shared rules file, remove duplicated logic in the page, decide whether to keep the old direct-to-Microsoft mode, rewrite the README | Full suite plus an end-to-end test (propose, review, apply, undo) |

## What you will see when you connect Claude Code (preview, verified in stage 4)

Claude Code asks for your approval at two points. First, when it finds a project-level server config
it asks whether to trust and enable that server. Second, it asks permission each time Claude wants to
run one of the server's tools, unless you have explicitly allowed that tool. Read-only tools are
reasonable to allow; the plan-proposing tool is worth leaving on "ask". The exact wording and
commands will be confirmed against Claude Code's current documentation when stage 4 is built.

## Decisions and open questions

- Language: Python (standard library only) for the engine, so it runs on Windows, macOS and Linux.
  The MCP stage will add one dependency (the official MCP SDK).
- Linux has no official OneDrive sync client; the community client or an rclone mount would be needed.
- Files that are "online only" (not downloaded) can be moved without downloading them. Reading their
  contents would download them, so the plan is to classify from names and metadata only.
