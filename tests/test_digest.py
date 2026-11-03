import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import openai
import pytz
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import download_new_papers
import relevancy
import utils


PAPER = {
    "title": "Example latency predictor",
    "authors": "Example Author",
    "main_page": "https://arxiv.org/abs/2611.00001",
    "abstract": "A sample abstract for offline testing.",
    "subjects": "Subjects:\nHardware Architecture (cs.AR); Machine Learning (cs.LG)",
}


class ParsingTests(unittest.TestCase):
    def test_subject_names_ignore_labels_and_whitespace(self):
        for subjects in (
            "Subjects:\n Machine Learning (cs.LG); Performance (cs.PF)",
            "Machine Learning (cs.LG);\n Performance (cs.PF)",
            "  Machine  Learning (cs.LG) ; Performance (cs.PF) ; ",
        ):
            with self.subTest(subjects=subjects):
                self.assertEqual(
                    relevancy.process_subject_fields(subjects),
                    ["Machine Learning", "Performance"],
                )

    def test_download_uses_abstract_link_and_normalizes_html_text(self):
        html = (ROOT / "tests/fixtures/arxiv-list.html").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            old_cwd = Path.cwd()
            try:
                os.chdir(directory)
                with patch("urllib.request.urlopen", return_value=io.BytesIO(html)) as fetch:
                    papers = download_new_papers.get_papers("cs")
                fetch.assert_called_once_with("https://arxiv.org/list/cs/new", timeout=30)
                self.assertEqual(len(papers), 1)
                paper = papers[0]
                self.assertEqual(paper["main_page"], PAPER["main_page"])
                self.assertEqual(paper["title"], PAPER["title"])
                self.assertEqual(paper["authors"], PAPER["authors"])
                self.assertEqual(relevancy.process_subject_fields(paper["subjects"]), [
                    "Hardware Architecture", "Machine Learning", "Performance",
                ])
            finally:
                os.chdir(old_cwd)

    def test_context_length_retries_are_bounded(self):
        error = openai.error.InvalidRequestError("Please reduce your prompt", param=None)
        with patch.object(openai.ChatCompletion, "create", side_effect=error) as create:
            with self.assertRaises(openai.error.InvalidRequestError):
                utils.openai_completion("test", utils.OpenAIDecodingArguments(), model_name="test")
        self.assertEqual(create.call_count, 4)

    def test_connection_failures_stop_without_outer_retries(self):
        for error_type in (openai.error.APIConnectionError, openai.error.Timeout):
            with self.subTest(error=error_type.__name__):
                error = error_type("Connection timed out")
                with patch.object(openai.ChatCompletion, "create", side_effect=error) as create:
                    with patch("utils.time.sleep") as sleep:
                        with self.assertLogs(level="WARNING") as logs:
                            with self.assertRaises(error_type):
                                utils.openai_completion("test", utils.OpenAIDecodingArguments(), model_name="test")
                self.assertEqual(create.call_count, 1)
                sleep.assert_not_called()
                self.assertIn("network access", " ".join(logs.output))
                self.assertNotIn("rate limit", " ".join(logs.output))

    def test_workflow_passes_all_three_secrets(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/daily_pipeline.yaml").read_text())
        steps = workflow["jobs"]["generate_and_send_digest"]["steps"]
        generate = next(step for step in steps if step.get("run", "").strip() == "python src/action.py")
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
            self.assertEqual(generate["env"][name], "${{ secrets." + name + " }}")


class CompatibleAPIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((self.path, self.headers.get("Authorization"), payload))
        result = {
            "id": "offline-test",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "finish_reason": self.server.finish_reason,
                "message": {"role": "assistant", "content": self.server.content},
            }],
        }
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CompatibleAPIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.requests = []
        self.server.finish_reason = "stop"
        self.set_score(9)

    def set_score(self, score):
        self.server.content = '1. ' + json.dumps({
            "Relevancy score": score, "Reasons for match": "与跨设备延迟预测相关。",
        }, ensure_ascii=False)

    def run_digest(self, papers=None, overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "src").symlink_to(ROOT / "src", target_is_directory=True)
            (directory / "data").mkdir()
            cache_date = date.fromtimestamp(datetime.now(tz=pytz.timezone("America/New_York")).timestamp())
            cache = directory / "data" / f"cs_{cache_date.strftime('%a, %d %b %y')}.jsonl"
            cache.write_text("".join(json.dumps(p) + "\n" for p in (papers if papers is not None else [PAPER])))
            (directory / "config.yaml").write_text(yaml.safe_dump({
                "topic": "Computer Science", "categories": ["Machine Learning"],
                "interest": "Cross-device latency prediction", "threshold": 6,
            }))
            env = dict(os.environ)
            for name in ("SENDGRID_API_KEY", "FROM_EMAIL", "TO_EMAIL", "OPENAI_ORG"):
                env.pop(name, None)
            env.update({
                "SENDGRID_API_KEY": "",
                "FROM_EMAIL": "",
                "TO_EMAIL": "",
                "OPENAI_API_KEY": "offline-test-key",
                "OPENAI_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/provider/v1/",
                "OPENAI_MODEL": "third-party-test-model",
                "NO_PROXY": "127.0.0.1",
            })
            env.update(overrides or {})
            result = subprocess.run(
                [sys.executable, str(ROOT / "src/action.py")], cwd=directory,
                env=env, capture_output=True, text=True, timeout=20,
            )
            output = directory / "digest.html"
            return result, output.read_text(encoding="utf-8") if output.exists() else None

    def test_cli_uses_environment_and_generates_paper_without_usage_field(self):
        result, html = self.run_digest()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(PAPER["title"], html)
        self.assertIn(PAPER["main_page"], html)
        self.assertIn("与跨设备延迟预测相关。", html)
        self.assertIn('<meta charset="utf-8">', html)
        self.assertIn("Papers after category filter: 1", result.stdout)
        self.assertEqual(len(self.server.requests), 1)
        path, authorization, payload = self.server.requests[0]
        self.assertEqual(path, "/provider/v1/chat/completions")
        self.assertEqual(authorization, "Bearer offline-test-key")
        self.assertEqual(payload["model"], "third-party-test-model")
        self.assertIn(PAPER["abstract"], payload["messages"][-1]["content"])

    def test_no_category_match_has_explanation_and_makes_no_api_call(self):
        paper = dict(PAPER, subjects="Subjects:\nInformation Retrieval (cs.IR)")
        result, html = self.run_digest([paper])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No papers matched the selected categories", html)
        self.assertEqual(self.server.requests, [])

    def test_below_threshold_has_a_distinct_explanation(self):
        self.set_score(3)
        result, html = self.run_digest()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No papers reached the relevance threshold (6/10)", html)
        self.assertNotIn(PAPER["title"], html)

    def test_missing_secrets_fail_before_api_call(self):
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
            with self.subTest(name=name):
                result, html = self.run_digest(overrides={name: " "})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Missing environment variable: " + name, result.stderr)
                self.assertIsNone(html)
        self.assertEqual(self.server.requests, [])

    def test_empty_truncated_and_incomplete_responses_fail(self):
        cases = [(None, "stop"), (self.server.content, "length"), ("No scores", "stop")]
        for content, finish_reason in cases:
            with self.subTest(content=content, finish_reason=finish_reason):
                self.server.content = content
                self.server.finish_reason = finish_reason
                result, html = self.run_digest()
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(html)


if __name__ == "__main__":
    unittest.main()
