"""Tests for utils/single_instance.py.

Why this exists: four copies of main_gui.py were found running at once.
Closing the orb hides it to the tray rather than quitting, so every launch
quietly added another instance — and each one answered every wake word.
"Open youtube" opened tabs in multiples and every reply was spoken in
chorus, which the user reported as two bugs ("opening tabs twice", "two
voices") with one cause.
"""

from __future__ import annotations

import pytest

from utils.single_instance import SingleInstance


@pytest.fixture
def name():
    """A per-test mutex name so tests cannot collide with each other or a
    genuinely running ULTRON."""
    import uuid

    return f"ULTRON-test-{uuid.uuid4().hex}"


class TestSingleInstance:
    def test_the_first_acquire_succeeds(self, name):
        lock = SingleInstance(name)
        try:
            assert lock.acquired
        finally:
            lock.release()

    def test_a_second_acquire_of_the_same_name_fails(self, name):
        first = SingleInstance(name)
        second = SingleInstance(name)
        try:
            assert first.acquired
            assert not second.acquired
        finally:
            second.release()
            first.release()

    def test_release_lets_the_next_acquire_succeed(self, name):
        first = SingleInstance(name)
        first.release()

        second = SingleInstance(name)
        try:
            assert second.acquired
        finally:
            second.release()

    def test_different_names_do_not_collide(self, name):
        first = SingleInstance(name)
        second = SingleInstance(name + "-other")
        try:
            assert first.acquired
            assert second.acquired
        finally:
            second.release()
            first.release()

    def test_release_twice_is_harmless(self, name):
        lock = SingleInstance(name)
        lock.release()
        lock.release()

    def test_a_dead_holder_does_not_wedge_the_lock(self, name):
        """The reason this is a kernel mutex and not a lockfile.

        The four stale instances were cleaned up with Stop-Process. A
        lockfile survives a killed process and locks the user out of their
        own assistant until someone deletes it; a kernel object is released
        by the OS the moment its holder dies.
        """
        import subprocess
        import sys

        # A child grabs the lock and exits without releasing.
        code = (
            "from utils.single_instance import SingleInstance;"
            f"lock = SingleInstance({name!r});"
            "assert lock.acquired"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            cwd=".",
        )

        lock = SingleInstance(name)
        try:
            assert lock.acquired
        finally:
            lock.release()
