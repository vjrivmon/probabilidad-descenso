"""Tests del modelo de datos RelegationProbabilities / TeamProbabilities."""

from __future__ import annotations

import pytest

from descenso.domain.probabilities import RelegationProbabilities, TeamProbabilities


def _tp(team: str, p: float) -> TeamProbabilities:
    return TeamProbabilities(
        team=team,
        p_relegation=p,
        p_by_position={1: 1.0 - p, 2: p},
        expected_points=40.0,
        expected_position=2.0,
    )


def test_p_safe_es_complementario() -> None:
    tp = _tp("barcelona", 0.12)
    assert tp.p_safe == pytest.approx(0.88)


def test_ranked_ordena_de_mayor_a_menor_probabilidad() -> None:
    rp = RelegationProbabilities(
        n_sims=1000,
        teams=[_tp("a", 0.05), _tp("b", 0.80), _tp("c", 0.30)],
    )
    ordered = rp.ranked()
    assert [t.team for t in ordered] == ["b", "c", "a"]


def test_ranked_con_un_equipo() -> None:
    rp = RelegationProbabilities(n_sims=100, teams=[_tp("solo", 0.5)])
    assert rp.ranked()[0].team == "solo"


def test_seed_none_es_valido() -> None:
    rp = RelegationProbabilities(n_sims=100, teams=[], seed=None)
    assert rp.seed is None


def test_ranked_lista_vacia() -> None:
    rp = RelegationProbabilities(n_sims=100, teams=[])
    assert rp.ranked() == []
