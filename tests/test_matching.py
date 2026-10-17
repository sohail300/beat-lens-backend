"""Match scoring and the confidence rule."""
from app.core.matching import analyze_relative_timing, confident_match
from app.models.schemas import Match


def _match(song_id: int, score: float) -> Match:
    return Match(song_id=song_id, song_title="t", song_artist="a", youtube_id="", timestamp=0, score=score)


def test_score_counts_hashes_with_a_consistent_offset():
    # Three hashes agree on a +10 s offset; two are scattered noise
    times = [(0, 10_000), (500, 10_500), (900, 10_900), (100, 40_000), (200, 3_000)]
    assert analyze_relative_timing({1: times}) == {1: 3.0}


def test_confident_match_accepts_a_clear_winner():
    assert confident_match([_match(1, 40), _match(2, 9)]) == [_match(1, 40)]


def test_confident_match_rejects_a_close_runner_up():
    assert confident_match([_match(1, 12), _match(2, 9)]) == []


def test_confident_match_rejects_a_low_score():
    assert confident_match([_match(1, 5)]) == []


def test_confident_match_handles_no_candidates():
    assert confident_match([]) == []
