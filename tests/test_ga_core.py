import tempfile
import unittest
from pathlib import Path

from ga_core import AgentHandler, AgentLoop, LLMResponse, ToolCall
from ga_core.llm import FakeClient
from ga_core.memory import build_system_prompt, load_l0
from ga_core.tools import code_run, file_patch, file_read, file_write, TOOLS_SCHEMA


class TestTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_write_read_roundtrip(self):
        self.assertEqual(file_write("a.txt", "hello\nworld\n", self.ws)["status"], "ok")
        result = file_read("a.txt", self.ws)
        self.assertEqual(result["status"], "ok")
        self.assertIn("hello", result["content"])

    def test_file_patch_requires_unique_match(self):
        file_write("a.txt", "x\ny\n", self.ws)
        self.assertEqual(file_patch("a.txt", "x", "X", self.ws)["status"], "ok")
        self.assertEqual(file_patch("a.txt", "missing", "Y", self.ws)["status"], "error")
        file_write("b.txt", "dup\ndup\n", self.ws)
        self.assertEqual(file_patch("b.txt", "dup", "D", self.ws)["status"], "error")

    def test_path_escape_blocked(self):
        result = file_write("../escape.txt", "x", self.ws)
        self.assertEqual(result["status"], "error")
        self.assertIn("PermissionError", result["msg"])
        self.assertFalse((self.ws.parent / "escape.txt").exists())

    def test_code_run_python(self):
        result = code_run("print(6 * 7)", "python", 30, self.ws)
        self.assertEqual(result["status"], "ok")
        self.assertIn("42", result["stdout"])

    def test_code_run_reports_error(self):
        result = code_run("raise SystemExit(3)", "python", 30, self.ws)
        self.assertEqual(result["status"], "error")

    def test_schema_has_nine_tools(self):
        self.assertEqual(len(TOOLS_SCHEMA), 9)


class TestLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_loop_executes_tool_then_finishes(self):
        client = FakeClient([
            LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="file_write", arguments={"path": "out.txt", "content": "ok"})]),
            LLMResponse(content="完成"),
        ])
        loop = AgentLoop(client, AgentHandler(workspace=self.ws), "system", max_turns=5, verbose=False)
        result = loop.run("写文件")
        self.assertEqual(result["result"], "DONE")
        self.assertEqual((self.ws / "out.txt").read_text(encoding="utf-8"), "ok")

    def test_working_checkpoint(self):
        client = FakeClient([
            LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="update_working_checkpoint", arguments={"key_info": "关键事实"})]),
            LLMResponse(content="完成"),
        ])
        loop = AgentLoop(client, AgentHandler(workspace=self.ws), "system", max_turns=5, verbose=False)
        result = loop.run("记一下")
        self.assertEqual(result["working"]["key_info"], "关键事实")

    def test_unknown_tool_feeds_back_error(self):
        client = FakeClient([
            LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="nope", arguments={})]),
            LLMResponse(content="完成"),
        ])
        loop = AgentLoop(client, AgentHandler(workspace=self.ws), "system", max_turns=5, verbose=False)
        self.assertEqual(loop.run("x")["result"], "DONE")

    def test_max_turns(self):
        responses = [LLMResponse(content="", tool_calls=[ToolCall(id=f"c{i}", name="update_working_checkpoint", arguments={"key_info": "x"})]) for i in range(5)]
        loop = AgentLoop(FakeClient(responses), AgentHandler(workspace=self.ws), "system", max_turns=5, verbose=False)
        self.assertEqual(loop.run("x")["result"], "MAX_TURNS_EXCEEDED")

    def test_ask_user_without_input_exits(self):
        client = FakeClient([LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="ask_user", arguments={"question": "继续吗"})])])
        loop = AgentLoop(client, AgentHandler(workspace=self.ws), "system", max_turns=5, verbose=False)
        self.assertEqual(loop.run("x")["result"], "WAITING_USER")


class TestMemory(unittest.TestCase):
    def test_system_prompt_contains_l0(self):
        prompt = build_system_prompt()
        l0 = load_l0()
        self.assertIn("L0", prompt)
        if l0:
            self.assertIn(l0.splitlines()[0][:20], prompt)


if __name__ == "__main__":
    unittest.main()
