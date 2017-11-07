# Ref: https://bugs.python.org/issue8800

import time
import threading
try:
    # python 2.7
    from thread import get_ident
except ImportError:
    from threading import get_ident
import unittest

from rwlock import RWLock

try:
    # python 3
    from test import support as support
except ImportError:
    # python 2.7
    from test import test_support as support


def _wait():
    # A crude wait/yield function not relying on synchronization primitives.
    time.sleep(0.01)


class Bunch(object):
    """
    A bunch of threads.
    """
    def __init__(self, f, n, wait_before_exit=False):
        """
        Construct a bunch of `n` threads running the same function `f`.
        If `wait_before_exit` is True, the threads won't terminate until
        do_finish() is called.
        """
        self.f = f
        self.n = n
        self.started = []
        self.finished = []
        self._can_exit = not wait_before_exit

        def task():
            tid = get_ident()
            self.started.append(tid)
            try:
                f()
            finally:
                self.finished.append(tid)
                while not self._can_exit:
                    _wait()
        for _ in range(n):
            threading.Thread(target=task).start()

    def wait_for_started(self):
        while len(self.started) < self.n:
            _wait()

    def wait_for_finished(self):
        while len(self.finished) < self.n:
            _wait()

    def do_finish(self):
        self._can_exit = True


class RWLockTests(unittest.TestCase):
    """
    Tests for RWLock objects
    """
    def setUp(self):
        self._threads = support.threading_setup()

    def tearDown(self):
        support.threading_cleanup(*self._threads)
        support.reap_children()

    def locktype(self):
        return RWLock()

    def rwlocktype(self):
        return RWLock()

    def test_many_readers(self):
        lock = self.rwlocktype()
        N = 5
        locked = []
        nlocked = []

        def f():
            with lock.reader_lock:
                locked.append(1)
                _wait()
                nlocked.append(len(locked))
                _wait()
                locked.pop(-1)
        Bunch(f, N).wait_for_finished()
        self.assertTrue(max(nlocked) > 1)

    def test_reader_recursion(self):
        lock = self.rwlocktype()
        N = 5
        locked = []
        nlocked = []

        def f():
            with lock.reader_lock:
                with lock.reader_lock:
                    locked.append(1)
                    _wait()
                    nlocked.append(len(locked))
                    _wait()
                    locked.pop(-1)
        Bunch(f, N).wait_for_finished()
        self.assertTrue(max(nlocked) > 1)

    def test_writer_recursion(self):
        lock = self.rwlocktype()
        N = 5
        locked = []
        nlocked = []

        def f():
            with lock.writer_lock:
                with lock.writer_lock:
                    locked.append(1)
                    _wait()
                    nlocked.append(len(locked))
                    _wait()
                    locked.pop(-1)
        Bunch(f, N).wait_for_finished()
        self.assertEqual(max(nlocked), 1)

    def test_writer_recursionfail(self):
        lock = self.rwlocktype()
        N = 5
        locked = []

        def f():
            with lock.reader_lock:
                self.assertRaises(RuntimeError, lock.writer_lock.acquire)
                locked.append(1)
        Bunch(f, N).wait_for_finished()
        self.assertEqual(len(locked), N)

    def test_readers_writers(self):
        lock = self.rwlocktype()
        N = 5
        rlocked = []
        wlocked = []
        nlocked = []

        def r():
            with lock.reader_lock:
                rlocked.append(1)
                _wait()
                nlocked.append((len(rlocked), len(wlocked)))
                _wait()
                rlocked.pop(-1)

        def w():
            with lock.writer_lock:
                wlocked.append(1)
                _wait()
                nlocked.append((len(rlocked), len(wlocked)))
                _wait()
                wlocked.pop(-1)
        b1 = Bunch(r, N)
        b2 = Bunch(w, N)
        b1.wait_for_finished()
        b2.wait_for_finished()
        r, w, = zip(*nlocked)
        self.assertTrue(max(r) > 1)
        self.assertEqual(max(w), 1)
        for r, w in nlocked:
            if w:
                self.assertEqual(r, 0)
            if r:
                self.assertEqual(w, 0)

    def test_writer_success(self):
        """Verify that a writer can get access"""
        lock = self.rwlocktype()
        N = 5
        d = {'reads': 0, 'writes': 0}

        def r():
            # read until we achive write successes
            while d['writes'] < 2:
                with lock.reader_lock:
                    d['reads'] += 1

        def w():
            while d['reads'] == 0:
                _wait()
            for _ in range(2):
                _wait()
                with lock.writer_lock:
                    d['writes'] += 1

        b1 = Bunch(r, N)
        b2 = Bunch(w, 1)
        b1.wait_for_finished()
        b2.wait_for_finished()
        self.assertEqual(d['writes'], 2)
        # uncomment this to view performance
        #print(writes, reads)
