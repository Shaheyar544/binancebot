"""Economic event manager enforcing 24h pre/post high-impact news lock and reassessment."""

from collections.abc import Sequence

from src.macro.models import EconomicEvent, EventImpact, NewsLockState


class EconomicEventManager:
    """Manages economic event calendar and enforces trading lockout windows."""

    PRE_EVENT_LOCK_MS = 24 * 3600 * 1000  # 24 hours in ms
    POST_EVENT_LOCK_MS = 24 * 3600 * 1000  # 24 hours in ms
    REASSESSMENT_WINDOW_MS = 24 * 3600 * 1000  # Subsequent 24 hours

    def __init__(self, events: Sequence[EconomicEvent] | None = None) -> None:
        self.events: list[EconomicEvent] = list(events or [])

    def add_event(self, event: EconomicEvent) -> None:
        """Add an economic calendar event."""
        self.events.append(event)

    def get_lock_state(self, timestamp_ms: int) -> NewsLockState:
        """Calculate active news lock state based on scheduled high-impact events."""
        is_reassessing = False

        for event in self.events:
            if event.impact != EventImpact.HIGH:
                continue

            event_time = event.timestamp_ms
            lock_start = event_time - self.PRE_EVENT_LOCK_MS
            lock_end = event_time + self.POST_EVENT_LOCK_MS
            reassess_end = lock_end + self.REASSESSMENT_WINDOW_MS

            # 1. Check strict 24h pre/post lock
            if lock_start <= timestamp_ms <= lock_end:
                return NewsLockState.NEWS_LOCK

            # 2. Check subsequent reassessment window
            if lock_end < timestamp_ms <= reassess_end:
                is_reassessing = True

        if is_reassessing:
            return NewsLockState.POST_NEWS_REASSESSMENT

        return NewsLockState.CLEAR

    def is_news_locked(self, timestamp_ms: int) -> bool:
        """Return True strictly during active NEWS_LOCK."""
        return self.get_lock_state(timestamp_ms) == NewsLockState.NEWS_LOCK
