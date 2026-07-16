import os
import time
import contextlib


class LockTimeoutError(Exception):
    pass


def acquire_lock(target_path, timeout=1.0, poll_interval=0.2):
    """Atomic O_CREAT|O_EXCL sentinel lock for target_path (creates
    '<target_path>.lock'). Retries on contention; raises LockTimeoutError
    if the lock isn't free within timeout."""
    lock_path = target_path + ".lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock_path
        except FileExistsError:
            if time.time() >= deadline:
                raise LockTimeoutError(f"Could not acquire lock for {target_path} within {timeout}s")
            time.sleep(poll_interval)


def release_lock(lock_path):
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass


@contextlib.contextmanager
def file_lock(target_path, timeout=1.0, poll_interval=0.2):
    lock_path = acquire_lock(target_path, timeout=timeout, poll_interval=poll_interval)
    try:
        yield
    finally:
        release_lock(lock_path)
