"""Keeps the Claude Code instructions honest: the project config must start the real server, and every
tool named in the docs must exist."""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters          # noqa: E402
from mcp.client.stdio import stdio_client                      # noqa: E402

REPO = Path(__file__).resolve().parent.parent
TOOLS = {"get_rules", "list_folder", "validate_manifest", "propose_plan", "list_context_files", "read_context_file"}


async def _list(params):
    async with stdio_client(params) as streams:
        async with ClientSession(streams[0], streams[1]) as s:
            await s.initialize()
            return ({t.name for t in (await s.list_tools()).tools},
                    {p.name for p in (await s.list_prompts()).prompts},
                    (await s.get_prompt("sort_folder", {"focus": "career files"})).messages[0].content.text)


def test_project_mcp_json_starts_the_real_server(tmp_path, monkeypatch):
    cfg = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["onedrive-sorter"]
    assert "type" not in cfg or cfg["type"] == "stdio"
    root = tmp_path / "OneDrive"
    root.mkdir()
    monkeypatch.setenv("ONEDRIVE_SORT_ROOT", str(root))
    args = [os.path.expandvars(a) for a in cfg["args"]]
    assert str(root) in args                                     # the variable the docs tell users to set
    params = StdioServerParameters(command=sys.executable if cfg["command"] in ("python", "python3") else cfg["command"],
                                   args=args + ["--proposals-dir", str(tmp_path / "p")], cwd=str(REPO),
                                   env={**os.environ})
    tools, prompts, text = asyncio.run(asyncio.wait_for(_list(params), 60))
    assert tools == TOOLS and prompts == {"sort_folder"}
    assert "career files" in text and "propose_plan" in text and "validate_manifest" in text
    assert "cannot move files" in text


def test_every_tool_the_docs_mention_exists():
    docs = (REPO / "docs" / "CLAUDE_CODE.md").read_text()
    named = set(re.findall(r"mcp__onedrive-sorter__([a-z_]+)", docs)) - {"sort_folder"}
    assert named and named <= TOOLS, named - TOOLS
    assert "mcp__onedrive-sorter__sort_folder" in docs


def test_the_settings_example_in_the_docs_is_valid_json_and_only_allows_read_only_tools():
    docs = (REPO / "docs" / "CLAUDE_CODE.md").read_text()
    block = re.search(r'```json\n(\{\n  "permissions".*?\n\})\n```', docs, re.S).group(1)
    allow = json.loads(block)["permissions"]["allow"]
    assert set(allow) == {f"mcp__onedrive-sorter__{t}" for t in TOOLS - {"propose_plan"}}
