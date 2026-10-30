"""Connection admission and shared monotonic request budgets."""

import math
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ParamSpec, TypeVar, cast

_deadline: ContextVar[float | None] = ContextVar("sentinel_request_deadline", default=None)
P = ParamSpec("P")
R = TypeVar("R")


def validate_timeout(value: int | float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be finite and positive")


def remaining(fallback: float = 5.0) -> float:
    deadline = _deadline.get()
    value = fallback if deadline is None else min(fallback, deadline - time.monotonic())
    if value <= 0:
        raise TimeoutError("request deadline exceeded")
    return value


@contextmanager
def budget(seconds: float) -> Iterator[None]:
    validate_timeout(seconds)
    prior = _deadline.get()
    end = time.monotonic() + seconds
    token = _deadline.set(min(prior, end) if prior is not None else end)
    try:
        yield
    finally:
        _deadline.reset(token)


def request_budget(method: Callable[P, R]) -> Callable[P, R]:
    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        self = cast(Any, args[0])
        with budget(self.config.request_timeout_seconds):
            return method(*args, **kwargs)

    return wrapped


def interrupt_socket(connection: socket.socket | None) -> None:
    if connection is None:
        return
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


@contextmanager
def socket_deadline(connection: socket.socket | None, seconds: float) -> Iterator[None]:
    timer = threading.Timer(remaining(seconds), interrupt_socket, args=(connection,))
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


@contextmanager
def timed_lock(lock: Any) -> Iterator[None]:
    if not lock.acquire(timeout=remaining(30.0)):
        raise TimeoutError("request expired waiting for analysis")
    try:
        remaining()
        yield
    finally:
        lock.release()


class BoundedHTTPServer(ThreadingHTTPServer):
    """Reject excess connections before starting a handler thread.

    A timer interrupts inbound socket IO, including request headers. Application
    code shares the same deadline for lock acquisition and upstream socket IO.
    """

    daemon_threads = True
    request_queue_size = 32

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        max_connections: int = 32,
        request_timeout: float = 10.0,
    ) -> None:
        if type(max_connections) is not int or max_connections < 1:
            raise ValueError("max_connections must be positive")
        validate_timeout(request_timeout)
        self.request_timeout = request_timeout
        self.max_connections = max_connections
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            with budget(self.request_timeout), socket_deadline(request, self.request_timeout):
                request.settimeout(self.request_timeout)
                super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)

    def drain(self, timeout: float) -> bool:
        """Wait until all admitted handler threads release their connection slots."""
        acquired = 0
        deadline = time.monotonic() + max(0.0, timeout)
        while acquired < self.max_connections:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._slots.acquire(timeout=remaining):
                break
            acquired += 1
        for _ in range(acquired):
            self._slots.release()
        return acquired == self.max_connections
