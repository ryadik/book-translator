import threading
import time
from rate_limiter import RateLimiter

def worker(rl, results, index):
    with rl:
        results[index] = time.monotonic()

def test_rate_limiter():
    print("Starting rate limiter test (10 calls at 2 RPS)...")
    rl = RateLimiter(2.0) # 2 RPS
    threads = []
    results = [0] * 10

    start_time = time.monotonic()

    for i in range(10):
        t = threading.Thread(target=worker, args=(rl, results, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    end_time = time.monotonic()
    total_time = end_time - start_time

    print(f"Total time for 10 calls at 2 RPS: {total_time:.2f} seconds")
    
    # 10 calls at 2 RPS means 9 intervals of 0.5s = 4.5s minimum
    assert total_time >= 4.5, f"Expected >= 4.5 seconds, got {total_time}"
    print("Test passed successfully!")

if __name__ == "__main__":
    test_rate_limiter()
