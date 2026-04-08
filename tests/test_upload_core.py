import asyncio
import unittest
from contextlib import nullcontext

from duld.upload._core import _make_job_context, job_guard


class TestJobGuard(unittest.TestCase):
    def test_token_is_present_inside_context(self):
        s: set[str] = set()
        with job_guard(s, "token"):
            self.assertIn("token", s)

    def test_token_is_removed_after_context(self):
        s: set[str] = set()
        with job_guard(s, "token"):
            pass
        self.assertNotIn("token", s)

    def test_token_is_removed_on_exception(self):
        s: set[str] = set()
        try:
            with job_guard(s, "token"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertNotIn("token", s)

    def test_integer_token(self):
        s: set[int] = set()
        with job_guard(s, 42):
            self.assertIn(42, s)
        self.assertNotIn(42, s)

    def test_multiple_tokens(self):
        s: set[str] = set()
        with job_guard(s, "a"):
            with job_guard(s, "b"):
                self.assertIn("a", s)
                self.assertIn("b", s)
            self.assertNotIn("b", s)
        self.assertNotIn("a", s)


class TestMakeJobContext(unittest.TestCase):
    def test_zero_returns_nullcontext(self):
        ctx = _make_job_context(0)
        self.assertIsInstance(ctx, nullcontext)

    def test_nonzero_returns_semaphore(self):
        ctx = _make_job_context(3)
        self.assertIsInstance(ctx, asyncio.Semaphore)

    def test_semaphore_has_correct_initial_value(self):
        ctx = _make_job_context(5)
        self.assertIsInstance(ctx, asyncio.Semaphore)
        # Semaphore._value holds the count before any acquire
        self.assertEqual(ctx._value, 5)
