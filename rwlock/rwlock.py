# Ref: https://bugs.python.org/issue8800

from threading import Condition

try:
    from thread import get_ident
except ImportError:
    from threading import get_ident

import time


# The internal lock object managing the RWLock state.
class _RWLockCore(object):
    def __init__(self):
        self.cond = Condition()
        self.state = 0 # positive is shared count, negative exclusive count
        self.waiting = 0
        self.owning = [] # threads will be few, so a list is not inefficient

    # Acquire the lock in read mode.
    def acquire_read(self, timeout=None):
        with self.cond:
            return self.wait_for(self._acquire_read, timeout)

    def _acquire_read(self):
        if self.state < 0:
            # lock is in write mode.  See if it is ours and we can recurse
            return self._acquire_write()

        # Implement "exclusive bias" giving exclusive lock priority.
        me = get_ident()
        if not self.waiting:
            ok = True # no exclusive acquires waiting.
        else:
            # Recursion must have the highest priority, otherwise we deadlock
            ok = me in self.owning

        if ok:
            self.state += 1
            self.owning.append(me)
        return ok

    # Acquire the lock in write mode.  A 'waiting' count is maintainded,
    # ensurring that 'readers' will yield to writers.
    def acquire_write(self, timeout=None):
        with self.cond:
            self.waiting += 1
            try:
                return self.wait_for(self._acquire_write, timeout)
            finally:
                self.waiting -= 1

    def wait_for(self, predicate, timeout=None):
        """Wait until a condition evaluates to True.

        predicate should be a callable which result will be interpreted as a
        boolean value.  A timeout may be provided giving the maximum time to
        wait.

        """
        endtime = None
        waittime = timeout
        result = predicate()
        while not result:
            if waittime is not None:
                if endtime is None:
                    endtime = time.time() + waittime
                else:
                    waittime = endtime - time.time()
                    if waittime <= 0:
                        break
            self.cond.wait(waittime)
            result = predicate()
        return result

    def _acquire_write(self):
        #we can only take the write lock if no one is there, or we already hold the lock
        me = get_ident()
        if self.state == 0 or (self.state < 0 and me in self.owning):
            self.state -= 1
            self.owning.append(me)
            return True
        if self.state > 0 and me in self.owning:
            raise RuntimeError("cannot upgrade RWLock from read to write")
        return False

    # Release the lock
    def release(self):
        with self.cond:
            me = get_ident()
            try:
                self.owning.remove(get_ident())
            except ValueError:
                raise RuntimeError("cannot release an un-acquired lock")
            if self.state > 0:
                self.state -= 1
            else:
                self.state += 1
            if self.state == 0:
                self.cond.notify_all()

    # Interface for condition variable.  Must hold an exclusive lock since the
    # condition variable's state may be protected by the lock
    def _is_owned(self):
        return self.state < 0 and get_ident() in self.owning

    def _release_save(self):
        # In a exlusively locked state, get the recursion level and free the lock
        with self.cond:
            if get_ident() not in self.owning:
                raise RuntimeError("cannot release an un-acquired lock")
            r = self.owning
            self.owning = []
            self.state = 0
            self.cond.notify_all()
        return r

    def _acquire_restore(self, x):
        # Reclaim the exclusive lock at the old recursion level
        self.acquire_write()
        with self.cond:
            self.owning = x
            self.state = -len(x)

# Lock objects to access the _RWLockCore in reader or writer mode
class _ReaderLock:
    def __init__(self, lock):
        self.lock = lock

    @staticmethod
    def _timeout(blocking, timeout):
        # A few sanity checks to satisfy the unittests.
        if timeout < 0 and timeout != -1:
            raise ValueError("invalid timeout")
        if blocking:
            return timeout if timeout >= 0 else None
        if timeout > 0:
            raise ValueError("can't specify a timeout when non-blocking")
        return 0

    def acquire(self, blocking=True, timeout=-1):
        return self.lock.acquire_read(self._timeout(blocking, timeout))

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()

    def __exit__(self, exc, val, tb):
        self.release()

    def _is_owned(self):
        raise TypeError("a reader lock cannot be used with a Condition")

class _WriterLock(_ReaderLock):
    def acquire(self, blocking=True, timeout=-1):
        return self.lock.acquire_write(self._timeout(blocking, timeout))

    def _is_owned(self):
        return self.lock._is_owned()

    def _release_save(self):
        return self.lock._release_save()

    def _acquire_restore(self, arg):
        return self.lock._acquire_restore(arg)

class RWLock():
    # Doc shamelessly ripped off from Java
    """
    A RWLock maintains a pair of associated locks, one for read-only operations
    and one for writing. The read lock may be held simultaneously by multiple
    reader threads, so long as there are no writers. The write lock is exclusive.

    """
    core = _RWLockCore

    def __init__(self):
        core = self.core()
        self._reader_lock = _ReaderLock(core)
        self._writer_lock = _WriterLock(core)

    @property
    def reader_lock(self):
        """
        The lock used for read, or shared, access
        """
        return self._reader_lock

    @property
    def writer_lock(self):
        """
        The lock used for write, or exclusive, access
        """
        return self._writer_lock
