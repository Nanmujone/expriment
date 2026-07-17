import pytest

from english_player.player import PlaybackMode, PlaybackQueue, SongRef

SONGS = (SongRef("one", "One"), SongRef("two", "Two"), SongRef("three", "Three"))


def test_queue_rejects_invalid_start_index() -> None:
    with pytest.raises(ValueError):
        PlaybackQueue(SONGS, 3)


def test_sequential_queue_stops_at_both_ends() -> None:
    queue = PlaybackQueue(SONGS, 0, PlaybackMode.SEQUENTIAL)

    assert queue.previous_index() is None
    assert queue.next_index() == 1
    assert queue.with_index(2).next_index() is None


def test_repeat_list_wraps_and_single_item_repeats() -> None:
    queue = PlaybackQueue(SONGS, 2, PlaybackMode.REPEAT_LIST)
    single = PlaybackQueue((SONGS[0],), 0, PlaybackMode.REPEAT_LIST)

    assert queue.next_index() == 0
    assert queue.with_index(0).previous_index() == 2
    assert single.next_index() == 0
