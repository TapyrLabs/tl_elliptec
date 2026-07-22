"""Unit tests for the bus's priority request broker, no serial port involved."""
import threading
import time

import pytest

from tl_elliptec.bus import RequestPriority, _RequestBroker


def test_broker_runs_jobs_and_returns_results():
    broker = _RequestBroker()
    try:
        future = broker.submit(RequestPriority.COMMAND, lambda: 1 + 1)
        assert future.result(timeout=2) == 2
    finally:
        broker.stop()


def test_broker_propagates_exceptions_to_the_submitter():
    broker = _RequestBroker()
    try:
        def boom():
            raise ValueError("nope")

        future = broker.submit(RequestPriority.COMMAND, boom)
        with pytest.raises(ValueError):
            future.result(timeout=2)
    finally:
        broker.stop()


def test_broker_services_same_priority_jobs_in_submission_order():
    broker = _RequestBroker()
    try:
        order = []
        lock = threading.Lock()

        def record(name):
            with lock:
                order.append(name)

        futures = [
            broker.submit(RequestPriority.COMMAND, lambda n=n: record(n))
            for n in ("a", "b", "c")
        ]
        for f in futures:
            f.result(timeout=2)

        assert order == ["a", "b", "c"]
    finally:
        broker.stop()


def test_broker_lets_a_command_jump_ahead_of_already_queued_polling():
    """A high-priority (COMMAND) job submitted after a low-priority (POLL) job,
    while both are still waiting behind a busy worker, must run first."""
    broker = _RequestBroker()
    try:
        order = []
        lock = threading.Lock()
        release = threading.Event()

        def record(name, wait_for=None):
            if wait_for is not None:
                wait_for.wait(timeout=2)
            with lock:
                order.append(name)

        # Occupy the worker so the next two submissions have to queue up.
        blocker_future = broker.submit(RequestPriority.COMMAND, lambda: record("blocker", release))
        time.sleep(0.05)  # give the worker time to actually start on the blocker

        low_future = broker.submit(RequestPriority.POLL, lambda: record("low"))
        high_future = broker.submit(RequestPriority.COMMAND, lambda: record("high"))

        release.set()
        blocker_future.result(timeout=2)
        high_future.result(timeout=2)
        low_future.result(timeout=2)

        assert order == ["blocker", "high", "low"]
    finally:
        broker.stop()


def test_broker_rejects_submissions_after_stop():
    broker = _RequestBroker()
    broker.stop()
    future = broker.submit(RequestPriority.COMMAND, lambda: 1)
    with pytest.raises(RuntimeError):
        future.result(timeout=2)
