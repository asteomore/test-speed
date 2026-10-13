import re
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT = Path(__file__).with_name("speed_test.py")


class SpeedTestTests(unittest.TestCase):
    def setUp(self):
        self.request_count = 0
        self.active_requests = 0
        self.max_active_requests = 0
        self.sent_bytes = 0
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                test.request_count += 1
                test.active_requests += 1
                test.max_active_requests = max(
                    test.max_active_requests, test.active_requests
                )
                try:
                    if self.path == "/missing":
                        self.send_error(404)
                        return
                    if self.path == "/slow":
                        time.sleep(0.1)
                    payload = b"x" * (100_000 + test.request_count * 1_024)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    if self.path == "/truncated":
                        self.send_header("Content-Length", str(len(payload) + 100))
                    self.end_headers()
                    self.wfile.write(payload[:50_000])
                    self.wfile.flush()
                    time.sleep(0.002)
                    self.wfile.write(payload[50_000:])
                    test.sent_bytes += len(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    test.active_requests -= 1

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_script(self, path="/file", *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), self.url + path, *extra],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_downloads_ten_complete_responses_sequentially_and_reports_speed(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.request_count, 10)
        self.assertEqual(self.max_active_requests, 1)
        downloads = re.findall(r"Запрос \d+/10: (\d+) байт, ([\d.]+) с", result.stdout)
        self.assertEqual(len(downloads), 10)
        self.assertEqual(sum(int(size) for size, _ in downloads), self.sent_bytes)
        total_bytes = int(re.search(r"Всего скачано: (\d+) байт", result.stdout)[1])
        total_time = float(re.search(r"Суммарное время: ([\d.]+) с", result.stdout)[1])
        average_time = float(re.search(r"Среднее время: ([\d.]+) с", result.stdout)[1])
        speed = float(re.search(r"Скорость: ([\d.]+) Мбит/с", result.stdout)[1])
        self.assertEqual(total_bytes, self.sent_bytes)
        self.assertAlmostEqual(total_time, sum(float(t) for _, t in downloads), delta=0.00001)
        self.assertAlmostEqual(average_time, total_time / 10, delta=0.000001)
        self.assertAlmostEqual(speed, total_bytes * 8 / total_time / 1_000_000, delta=0.02)
        self.assertGreater(total_time, 0.02)

    def test_http_error_stops_measurement_without_success_summary(self):
        result = self.run_script("/missing")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("404", result.stderr)
        self.assertEqual(self.request_count, 1)
        self.assertNotIn("Скорость:", result.stdout)

    def test_timeout_stops_measurement_without_success_summary(self):
        result = self.run_script("/slow", "--timeout", "0.02")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Ошибка", result.stderr)
        self.assertEqual(self.request_count, 1)
        self.assertNotIn("Скорость:", result.stdout)

    def test_incomplete_response_is_not_reported_as_success(self):
        result = self.run_script("/truncated")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("не полностью", result.stderr)
        self.assertEqual(self.request_count, 1)
        self.assertNotIn("Скорость:", result.stdout)

    def test_invalid_timeout_is_rejected_before_network_request(self):
        for timeout in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=timeout):
                result = self.run_script("/file", "--timeout", timeout)
                self.assertEqual(result.returncode, 2)
                self.assertIn("положительным конечным числом", result.stderr)
                self.assertEqual(self.request_count, 0)


if __name__ == "__main__":
    unittest.main()
