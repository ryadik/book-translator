import threading
import time

class RateLimiter:
    """
    A thread-safe rate limiter that enforces a maximum requests-per-second (RPS) limit.
    """
    min_interval: float
    lock: threading.Lock
    last_call_time: float

    def __init__(self, max_rps: float):
        if max_rps <= 0:
            raise ValueError("max_rps must be greater than 0")
        self.min_interval = 1.0 / max_rps
        self.lock = threading.Lock()
        self.last_call_time = 0.0

    def __enter__(self):
        with self.lock:
            current_time = time.monotonic()
            elapsed = current_time - self.last_call_time
            wait_time = self.min_interval - elapsed

            if wait_time > 0:
                time.sleep(wait_time)

            # Update the last call time *after* the sleep
            self.last_call_time = time.monotonic()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None) -> None:
        pass
