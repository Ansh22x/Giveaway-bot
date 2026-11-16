import time
from collections import defaultdict, deque
from typing import Tuple


class SlidingWindowRateLimiter:
    """
    In-memory sliding window rate limiter:
    - 20 updates per user per minute
    - 60 updates per chat per minute
    """

    def __init__(self, user_limit: int = 20, chat_limit: int = 60, window_seconds: float = 60.0):
        self.user_limit = user_limit
        self.chat_limit = chat_limit
        self.window_seconds = window_seconds

        self._user_records = defaultdict(deque)
        self._chat_records = defaultdict(deque)

    def is_rate_limited(self, user_id: int, chat_id: int) -> Tuple[bool, str]:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Clean old user records
        user_dq = self._user_records[user_id]
        while user_dq and user_dq[0] < cutoff:
            user_dq.popleft()

        if len(user_dq) >= self.user_limit:
            return True, f"User rate limit exceeded (max {self.user_limit}/min). Please wait a moment."

        # Clean old chat records
        chat_dq = self._chat_records[chat_id]
        while chat_dq and chat_dq[0] < cutoff:
            chat_dq.popleft()

        if len(chat_dq) >= self.chat_limit:
            return True, f"Chat rate limit exceeded (max {self.chat_limit}/min). Please slow down."

        # Record update
        user_dq.append(now)
        chat_dq.append(now)
        return False, ""


rate_limiter = SlidingWindowRateLimiter()
