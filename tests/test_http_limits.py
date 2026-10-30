import http.client
import json
import socket
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler

from sentinel import http_limits
from sentinel.gateway import GatewayConfig, SentinelGateway
from sentinel.http_limits import BoundedHTTPServer
from sentinel.jsonrpc import JsonRpcError
from sentinel.service import create_service_server


def receive_until_closed(client):
    """Deadline shutdown may be EOF or a TCP abort/reset on Windows."""
    try:
        while client.recv(4096):
            pass
    except (ConnectionAbortedError, ConnectionResetError):
        pass
    # TimeoutError and unrelated OSErrors must still fail the deadline test.


@contextmanager
def running(server):
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


class HttpLimitTests(unittest.TestCase):
    def test_timeout_budget_and_lock_deadline_helpers(self):
        for invalid in (0, -1, float("nan"), float("inf"), True, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                http_limits.validate_timeout(invalid)

        self.assertEqual(http_limits.remaining(2), 2)
        token = http_limits._deadline.set(time.monotonic() - 1)
        try:
            with self.assertRaises(TimeoutError):
                http_limits.remaining()
        finally:
            http_limits._deadline.reset(token)

        with http_limits.budget(1):
            self.assertLessEqual(http_limits.remaining(2), 1)
            with http_limits.budget(0.5):
                self.assertLessEqual(http_limits.remaining(2), 0.5)
        self.assertEqual(http_limits.remaining(2), 2)

        lock = threading.Lock()
        with http_limits.timed_lock(lock):
            self.assertTrue(lock.locked())
        self.assertFalse(lock.locked())

        class UnavailableLock:
            def acquire(self, timeout):
                return False

        with self.assertRaisesRegex(TimeoutError, "waiting for analysis"):
            with http_limits.timed_lock(UnavailableLock()):
                self.fail("unavailable lock must not enter")

    def test_socket_deadline_and_interrupt_helpers(self):
        http_limits.interrupt_socket(None)
        connection = Mock()
        http_limits.interrupt_socket(connection)
        connection.shutdown.assert_called_once()
        connection.shutdown.side_effect = OSError("already closed")
        http_limits.interrupt_socket(connection)

        with patch.object(http_limits.threading, "Timer") as timer_type:
            timer = timer_type.return_value
            with http_limits.socket_deadline(connection, 1):
                timer.start.assert_called_once()
            timer.cancel.assert_called_once()

        with patch.object(http_limits, "remaining", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                with http_limits.socket_deadline(connection, 1):
                    self.fail("expired deadline must not enter")

    def test_request_budget_decorator_sets_and_resets_context(self):
        class Config:
            request_timeout_seconds = 0.5

        class Subject:
            config = Config()

        @http_limits.request_budget
        def read_budget(subject):
            return http_limits.remaining(2)

        remaining = read_budget(Subject())
        self.assertLessEqual(remaining, 0.5)
        self.assertEqual(http_limits.remaining(2), 2)

    def test_bounded_server_validates_and_releases_connection_slots(self):
        for options in (
            {"max_connections": 0},
            {"max_connections": True},
            {"request_timeout": 0},
            {"request_timeout": float("nan")},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                BoundedHTTPServer(("unused", 0), BaseHTTPRequestHandler, **options)

        server = BoundedHTTPServer.__new__(BoundedHTTPServer)
        server.max_connections = 1
        server.request_timeout = 1
        server._slots = threading.BoundedSemaphore(1)
        self.assertTrue(server.drain(0.01))
        self.assertTrue(server._slots.acquire(blocking=False))
        self.assertFalse(server.drain(0.001))
        server._slots.release()
        self.assertTrue(server.drain(0.01))

        server._slots = threading.BoundedSemaphore(1)
        request = Mock()
        with patch.object(http_limits.ThreadingHTTPServer, "process_request"):
            server.process_request(request, ("127.0.0.1", 1))
        self.assertFalse(server._slots.acquire(blocking=False))
        with patch.object(http_limits.ThreadingHTTPServer, "process_request_thread"):
            server.process_request_thread(request, ("127.0.0.1", 1))
        self.assertTrue(server._slots.acquire(blocking=False))
        server._slots.release()

        with patch.object(
            http_limits.ThreadingHTTPServer, "process_request", side_effect=RuntimeError
        ):
            with self.assertRaises(RuntimeError):
                server.process_request(request, ("127.0.0.1", 1))
        self.assertTrue(server._slots.acquire(blocking=False))
        server._slots.release()

        server._slots = threading.BoundedSemaphore(1)
        server._slots.acquire()
        overloaded = Mock()
        with patch.object(server, "shutdown_request") as shutdown:
            server.process_request(overloaded, ("127.0.0.1", 2))
        overloaded.sendall.assert_called_once()
        shutdown.assert_called_once_with(overloaded)
        server._slots.release()

    def test_server_handler_completion_releases_slot_and_error_handling_filters_timeouts(self):
        server = BoundedHTTPServer.__new__(BoundedHTTPServer)
        server.request_timeout = 1
        server.max_connections = 1
        server._slots = threading.BoundedSemaphore(1)
        request = Mock()
        server._slots.acquire()
        with patch.object(http_limits.ThreadingHTTPServer, "process_request_thread"):
            server.process_request_thread(request, ("127.0.0.1", 1))
        self.assertTrue(server._slots.acquire(blocking=False))
        server._slots.release()

        with patch.object(http_limits.sys, "exc_info", return_value=(None, TimeoutError(), None)):
            with patch.object(http_limits.ThreadingHTTPServer, "handle_error") as parent:
                server.handle_error(request, ("127.0.0.1", 1))
                parent.assert_not_called()
        with patch.object(http_limits.sys, "exc_info", return_value=(None, RuntimeError(), None)):
            with patch.object(http_limits.ThreadingHTTPServer, "handle_error") as parent:
                server.handle_error(request, ("127.0.0.1", 1))
                parent.assert_called_once()

    def test_shutdown_helper_accepts_eof_abort_and_reset(self):
        for ending in (
            b"",
            ConnectionAbortedError(10053, "aborted"),
            ConnectionResetError(10054, "reset"),
        ):
            client = Mock()
            client.recv.side_effect = [b"partial response", ending]
            receive_until_closed(client)
            self.assertEqual(client.recv.call_count, 2)

    def test_shutdown_helper_does_not_hide_timeouts_or_other_errors(self):
        for error in (TimeoutError("deadline not enforced"), OSError("unexpected failure")):
            client = Mock()
            client.recv.side_effect = error
            with self.assertRaises(type(error)):
                receive_until_closed(client)

    def test_connection_admission_and_slot_release(self):
        entered, release = threading.Event(), threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                entered.set()
                release.wait(2)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        with running(BoundedHTTPServer(("127.0.0.1", 0), Handler, max_connections=1)) as address:
            first = socket.create_connection(address, timeout=2)
            try:
                first.sendall(b"GET / HTTP/1.0\r\n\r\n")
                self.assertTrue(entered.wait(1))
                second = http.client.HTTPConnection(*address, timeout=2)
                try:
                    second.request("GET", "/")
                    self.assertEqual(second.getresponse().status, 503)
                except ConnectionError:
                    # Closing an unread overload request can produce a TCP reset
                    # on Windows; no handler is created in either rejection path.
                    pass
                second.close()
                release.set()
                self.assertIn(b"200", first.recv(4096))
                while first.recv(4096):
                    pass
            finally:
                release.set()
                first.close()
            # Retry briefly because the socket closes just before the slot releases.
            end = time.monotonic() + 1
            while True:
                third = http.client.HTTPConnection(*address, timeout=2)
                try:
                    third.request("GET", "/")
                    response = third.getresponse()
                    status = response.status
                    response.read()
                except ConnectionError:
                    status = 503
                third.close()
                if status == 200 or time.monotonic() > end:
                    break
                time.sleep(0.01)
            self.assertEqual(status, 200)

    def test_incomplete_headers_cannot_hold_connection(self):
        with running(create_service_server(port=0, request_timeout=0.2)) as address:
            client = socket.create_connection(address, timeout=2)
            try:
                start = time.monotonic()
                client.sendall(b"POST /v1/evaluate HTTP/1.1\r\nHost: localhost\r\n")
                receive_until_closed(client)
                self.assertLess(time.monotonic() - start, 1.5)
            finally:
                client.close()

    def test_trickling_body_has_total_deadline(self):
        with running(create_service_server(port=0, request_timeout=0.25)) as address:
            client = socket.create_connection(address, timeout=2)
            stop = threading.Event()

            def trickle():
                while not stop.wait(0.04):
                    try:
                        client.sendall(b" ")
                    except OSError:
                        return

            try:
                client.sendall(
                    b"POST /v1/evaluate HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1000\r\n\r\n"
                )
                sender = threading.Thread(target=trickle, daemon=True)
                sender.start()
                start = time.monotonic()
                receive_until_closed(client)
                self.assertLess(time.monotonic() - start, 1.5)
            finally:
                stop.set()
                client.close()
                sender.join()

    def test_slow_upstream_is_interrupted_and_never_learned(self):
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                for _ in range(40):
                    try:
                        self.wfile.write(b" ")
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.04)

            def log_message(self, *args):
                pass

        with running(BoundedHTTPServer(("127.0.0.1", 0), SlowHandler)) as address:
            gateway = SentinelGateway(
                GatewayConfig(
                    f"http://{address[0]}:{address[1]}",
                    "srv",
                    timeout_seconds=2,
                    request_timeout_seconds=0.25,
                    allowed_tools=("read",),
                )
            )
            start = time.monotonic()
            with self.assertRaises((JsonRpcError, TimeoutError)):
                gateway.handle(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {"name": "read"},
                        }
                    ).encode(),
                    {},
                )
            self.assertLess(time.monotonic() - start, 1.5)
            self.assertEqual(gateway.engine.profiles, {})


if __name__ == "__main__":
    unittest.main()
