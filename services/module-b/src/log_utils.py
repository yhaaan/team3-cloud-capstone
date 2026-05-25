from __future__ import annotations

from datetime import datetime


def log_with_timestamp(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")
