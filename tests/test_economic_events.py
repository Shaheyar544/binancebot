"""Tests for EconomicEventManager: 24h pre/post lock and reassessment windows."""

import pytest

from src.macro.event_manager import EconomicEventManager
from src.macro.models import EconomicEvent, EventImpact, NewsLockState


@pytest.fixture
def sample_fomc_event() -> EconomicEvent:
    return EconomicEvent(
        event_id="FOMC_2026_09",
        name="FOMC Interest Rate Decision",
        impact=EventImpact.HIGH,
        timestamp_ms=1700000000000,
        source="Federal Reserve",
    )


@pytest.fixture
def sample_low_impact_event() -> EconomicEvent:
    return EconomicEvent(
        event_id="LOW_IMPACT_01",
        name="Weekly Rig Count",
        impact=EventImpact.LOW,
        timestamp_ms=1700000000000,
        source="Baker Hughes",
    )


def test_24h_pre_event_lock(sample_fomc_event: EconomicEvent) -> None:
    """Timestamp within 24h prior to high-impact event triggers NEWS_LOCK."""
    manager = EconomicEventManager(events=[sample_fomc_event])
    event_t = sample_fomc_event.timestamp_ms

    # Exactly 23h 59m before -> NEWS_LOCK
    t_inside = event_t - (23 * 3600 + 59 * 60) * 1000
    state = manager.get_lock_state(t_inside)
    assert state == NewsLockState.NEWS_LOCK
    assert manager.is_news_locked(t_inside) is True

    # 24h 1m before -> CLEAR
    t_outside = event_t - (24 * 3600 + 60) * 1000
    assert manager.get_lock_state(t_outside) == NewsLockState.CLEAR
    assert manager.is_news_locked(t_outside) is False


def test_24h_post_event_lock_and_reassessment(sample_fomc_event: EconomicEvent) -> None:
    """Timestamp within 24h after event is NEWS_LOCK, subsequent 24h is POST_NEWS_REASSESSMENT."""
    manager = EconomicEventManager(events=[sample_fomc_event])
    event_t = sample_fomc_event.timestamp_ms

    # Exactly 23h 59m after -> still NEWS_LOCK
    t_post_lock = event_t + (23 * 3600 + 59 * 60) * 1000
    assert manager.get_lock_state(t_post_lock) == NewsLockState.NEWS_LOCK
    assert manager.is_news_locked(t_post_lock) is True

    # 24h 5m after -> POST_NEWS_REASSESSMENT
    t_reassess = event_t + (24 * 3600 + 300) * 1000
    assert manager.get_lock_state(t_reassess) == NewsLockState.POST_NEWS_REASSESSMENT
    # In reassessment, new entries require fresh technical re-qualification
    # (not locked by news alone)
    assert manager.is_news_locked(t_reassess) is False


def test_low_impact_event_does_not_trigger_lock(sample_low_impact_event: EconomicEvent) -> None:
    """Low or medium impact events do not cause NEWS_LOCK."""
    manager = EconomicEventManager(events=[sample_low_impact_event])
    event_t = sample_low_impact_event.timestamp_ms

    # 1 hour before low impact event -> CLEAR
    t_check = event_t - 3600000
    assert manager.get_lock_state(t_check) == NewsLockState.CLEAR
    assert manager.is_news_locked(t_check) is False
