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
            "artcraft_develop",
            "artcraft_audio_basic",
            "artcraft_video_basic",
            "artcraft_recipe",
        }
        self.assertEqual(set(mcp_server.EXPOSED_TOOLS.keys()), expected_tools)
        self.assertEqual(len(mcp_server.EXPOSED_TOOLS), 14)

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
        self.assertEqual(len(tools), 14)
        tool_names = {t["name"] for t in tools}
        self.assertIn("artcraft_build_review", tool_names)
        self.assertIn("artcraft_job", tool_names)
        self.assertIn("photocraft_spot_heal", tool_names)
        self.assertIn("artcraft_develop", tool_names)
        self.assertIn("artcraft_audio_basic", tool_names)
        self.assertIn("artcraft_video_basic", tool_names)
        self.assertIn("artcraft_recipe", tool_names)
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
        self.assertIn("capabilities", payload)
        self.assertIn("available_tools", payload["capabilities"])

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
        req2 = (
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode("utf-8") + b"\n"
        )
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
        self.assertEqual(len(resp2["result"]["tools"]), 14)

    def test_content_length_framing(self) -> None:
        payload = json.dumps({"jsonrpc": "2.0", "id": "cl-1", "method": "ping"}).encode("utf-8")
        raw = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8") + payload
        in_stream = io.BytesIO(raw)
        msg = mcp_server.read_message(in_stream)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["id"], "cl-1")
        self.assertEqual(msg["method"], "ping")

    def test_content_length_rejects_invalid_and_oversized_and_truncated(self) -> None:
        valid_payload = json.dumps({"jsonrpc": "2.0", "id": "bad", "method": "ping"}).encode(
            "utf-8"
        )

        # Negative Content-Length must not fall back to stream.read(-1)
        neg_raw = b"Content-Length: -1\r\n\r\n" + valid_payload
        self.assertIsNone(mcp_server.read_message(io.BytesIO(neg_raw)))

        # Zero Content-Length must return None
        zero_raw = b"Content-Length: 0\r\n\r\n"
        self.assertIsNone(mcp_server.read_message(io.BytesIO(zero_raw)))

        # Oversized Content-Length must return None before reading body
        class _FailReadStream:
            def __init__(self, header: bytes) -> None:
                self._buf = io.BytesIO(header)

            def readline(self, limit: int = -1) -> bytes:
                return self._buf.readline(limit)

            def read(self, size: int = -1) -> bytes:
                raise AssertionError(
                    f"stream.read({size}) should not be called for oversized frame"
                )

        oversized = mcp_server.MAX_MESSAGE_BYTES + 1
        header = f"Content-Length: {oversized}\r\n\r\n".encode()
        self.assertIsNone(mcp_server.read_message(_FailReadStream(header)))

        # Truncated body (even if valid JSON prefix) must return None
        truncated_json = b'{"a":1}'
        trunc_raw = f"Content-Length: {len(truncated_json) + 20}\r\n\r\n".encode() + truncated_json
        self.assertIsNone(mcp_server.read_message(io.BytesIO(trunc_raw)))

    def test_tools_call_missing_input_sets_is_error_true(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "err-missing",
            "method": "tools/call",
            "params": {
                "name": "artcraft_inspect",
                "arguments": {"path": str(self.test_dir / "does_not_exist.png")},
            },
        }
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        self.assertTrue(resp["result"]["isError"])
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertFalse(payload["ok"])

    def test_tools_call_failed_cli_sets_is_error_true(self) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "err-cli",
            "method": "tools/call",
            "params": {
                "name": "photocraft_spot_heal",
                "arguments": {
                    "input_path": str(self.test_dir / "missing.png"),
                    "output_path": str(self.test_dir / "out.png"),
                    "region": [0, 0, 10, 10],
                    "points": [[5, 5]],
                },
            },
        }
        resp = mcp_server.process_message(req)
        self.assertIsNotNone(resp)
        self.assertTrue(resp["result"]["isError"])
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertFalse(payload["ok"])

    def test_tools_call_clarification_and_quality_rejection_not_is_error(self) -> None:
        # 1. Clarification gate (3:4 source for 8x10 borderless) -> isError=False
        src = self.test_dir / "portrait_3x4.png"
        out = self.test_dir / "print_8x10.png"
        Image.new("RGB", (300, 400), color=(120, 120, 120)).save(src)
        req_clarify = {
            "jsonrpc": "2.0",
            "id": "clarify-1",
            "method": "tools/call",
            "params": {
                "name": "artcraft_prepare_print",
                "arguments": {
                    "input_path": str(src),
                    "output_path": str(out),
                    "width_in": 8.0,
                    "height_in": 10.0,
                    "fit_mode": "borderless",
                },
            },
        }
        resp_c = mcp_server.process_message(req_clarify)
        self.assertFalse(resp_c["result"]["isError"])
        clarify_payload = json.loads(resp_c["result"]["content"][0]["text"])
        self.assertEqual(clarify_payload["status"], "needs_clarification")

        # 2. Quality assessment rejecting a no-op output -> isError=False
        same_out = self.test_dir / "same_out.png"
        Image.new("RGB", (300, 400), color=(120, 120, 120)).save(same_out)
        req_review = {
            "jsonrpc": "2.0",
            "id": "review-noop",
            "method": "tools/call",
            "params": {
                "name": "artcraft_build_review",
                "arguments": {
                    "source_path": str(src),
                    "output_path": str(same_out),
                    "working_dir": str(self.test_dir / "rev"),
                    "region": [10, 10, 40, 40],
                },
            },
        }
        resp_r = mcp_server.process_message(req_review)
        self.assertFalse(resp_r["result"]["isError"])
        rev_payload = json.loads(resp_r["result"]["content"][0]["text"])
        self.assertFalse(rev_payload["passed"])
        flag_ids = [f["id"] for f in rev_payload["flags"]]
        self.assertIn("untouched_scratch", flag_ids)

    def test_tools_call_rejects_non_object_params_or_arguments(self) -> None:
        bad_params_req = {
            "jsonrpc": "2.0",
            "id": "bad-params",
            "method": "tools/call",
            "params": ["artcraft_status"],
        }
        resp_p = mcp_server.process_message(bad_params_req)
        self.assertIsNotNone(resp_p)
        self.assertEqual(resp_p["error"]["code"], -32602)

        bad_args_req = {
            "jsonrpc": "2.0",
            "id": "bad-args",
            "method": "tools/call",
            "params": {"name": "artcraft_status", "arguments": ["bad"]},
        }
        resp_a = mcp_server.process_message(bad_args_req)
        self.assertIsNotNone(resp_a)
        self.assertEqual(resp_a["error"]["code"], -32602)
