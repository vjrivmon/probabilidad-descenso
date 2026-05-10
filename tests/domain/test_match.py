"""Tests de la entidad Match (validaciones básicas)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from descenso.domain.match import Match, MatchStatus


def test_pending_match_has_no_goals() -> None:
    m = Match(season=2025, gameweek=33, home_team="levante", away_team="osasuna")
    assert m.status is MatchStatus.PENDING


def test_played_match() -> None:
    m = Match(
        season=2025,
        gameweek=33,
        home_team="levante",
        away_team="osasuna",
        home_goals=3,
        away_goals=2,
    )
    assert m.status is MatchStatus.PLAYED
    assert m.key == (2025, "levante", "osasuna")


def test_partial_score_rejected() -> None:
    with pytest.raises(ValidationError):
        Match(season=2025, gameweek=1, home_team="a", away_team="b", home_goals=1)


def test_absurd_score_rejected() -> None:
    with pytest.raises(ValidationError):
        Match(season=2025, gameweek=1, home_team="a", away_team="b", home_goals=99, away_goals=0)


def test_team_cannot_play_itself() -> None:
    with pytest.raises(ValidationError):
        Match(season=2025, gameweek=1, home_team="a", away_team="a")
