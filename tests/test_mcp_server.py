"""Tests for the ArtCraft stdio MCP server."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from artcraft_plugin import mcp_server


class TestArtCraftMcpServer(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_registered_tools_count_and_names(self) -> None:
        expected_tools = {
            "artcraft_status",
            "artcraft_inspect",
            "artcraft_prepare_inspection",
            "artcraft_prepare_print",
            "artcraft_verify_edit",
            "photocraft_spot_heal",
            "artcraft_restore_step",
            "artcraft_checkpoint",
            "artcraft_build_review",
            "artcraft_job",
        }
        self.assertEqual(set(mcp_server.EXPOSED_TOOLS.keys()), expected_tools)
        self.assertEqual(len(mcp_server.EXPOSED_TOOLS), 10)

    def test_initialize_and_ping(self) -> None:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        resp = mcp_server.process_message(init_req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", resp["result"]["capabilities"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "artcraft-plugin")

        ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        ping_resp = mcp_server.process_message(ping_req)
        self.assertEqual(ping_resp["id"], 2)
        self.assertEqual(ping_resp["result"], {})

        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        notif_resp = mcp_server.process_message(notif)
        self.assertIsNone(notif_resp)

    def test_tools_list(self) -> None:
        req = {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list"}
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), 10)
        tool_names = {t["name"] for t in tools}
        self.assertIn("artcraft_build_review", tool_names)
        self.assertIn("artcraft_job", tool_names)
        self.assertIn("photocraft_spot_heal", tool_names)
        for t in tools:
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_tools_call_status(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "artcraft_status", "arguments": {}},
        }
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        self.assertFalse(resp["result"].get("isError", False))
        content = resp["result"]["content"]
        self.assertEqual(len(content), 1)
        payload = json.loads(content[0]["text"])
        self.assertTrue(payload["ok"])
        self.assertIn("apps", payload)

    def test_tools_call_inspect(self) -> None:
        img_path = self.test_dir / "sample.png"
        img = Image.new("RGB", (120, 80), color=(100, 150, 200))
        img.save(img_path)

        req = {
            "jsonrpc": "2.0",
            "id": "inspect-1",
            "method": "tools/call",
            "params": {
                "name": "artcraft_inspect",
                "arguments": {"path": str(img_path)},
            },
        }
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        content = resp["result"]["content"]
        payload = json.loads(content[0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["width"], 120)
        self.assertEqual(payload["height"], 80)

    def test_tools_call_unknown_tool(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "err-1",
            "method": "tools/call",
            "params": {"name": "unknown_tool", "arguments": {}},
        }
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("Unknown ArtCraft tool", resp["result"]["content"][0]["text"])

    def test_unknown_method_returns_error(self) -> None:
        req = {"jsonrpc": "2.0", "id": 99, "method": "custom/unknown"}
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_stdio_pipeline_stream(self) -> None:
        req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode("utf-8") + b"\n"
        req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode("utf-8") + b"\n"
        in_stream = io.BytesIO(req1 + req2)
        out_stream = io.BytesIO()

        mcp_server.run_server(in_stream=in_stream, out_stream=out_stream)

        out_stream.seek(0)
        lines = out_stream.readlines()
        self.assertEqual(len(lines), 2)
        resp1 = json.loads(lines[0].decode("utf-8"))
        resp2 = json.loads(lines[1].decode("utf-8"))
        self.assertEqual(resp1["id"], 1)
        self.assertEqual(resp1["result"], {})
        self.assertEqual(resp2["id"], 2)
        self.assertEqual(len(resp2["result"]["tools"]), 10)

    def test_content_length_framing(self) -> None:
        payload = json.dumps({"jsonrpc": "2.0", "id": "cl-1", "method": "ping"}).encode("utf-8")
        raw = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8") + payload
        in_stream = io.BytesIO(raw)
        msg = mcp_server.read_message(in_stream)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["id"], "cl-1")
        self.assertEqual(msg["method"], "ping")
