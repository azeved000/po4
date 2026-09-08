"""O MTZ não pode cortar solução ótima.

As restrições (6) são redundantes: as restrições de tempo (4') já impedem
subciclos, porque um ciclo implicaria ``C[i] > C[i]``. Elas entram só para
fortalecer a relaxação linear. Um erro de sinal ou um limitante trocado nelas
não deixa o modelo inviável — ele continua devolvendo "Optimal", só que com um
valor **pior**, e nada mais no projeto acusaria isso. Este arquivo é a proteção
contra esse defeito específico.
"""

from __future__ import annotations

import pytest

from rubbertech.instancias import (
    estagio_1_maquina_unica,
    estagio_2_setup,
    estagio_3_subciclos,
    estagio_4_elegibilidade,
)
from rubbertech.modelo import ConfigModelo, construir
from rubbertech.solver import resolver
from rubbertech.validacao import forca_bruta

CASOS = [
    ("estagio_1", estagio_1_maquina_unica(n=4, seed=11)),
    ("estagio_2", estagio_2_setup(n=4, seed=12)),
    ("estagio_3", estagio_3_subciclos(n=4, seed=13)),
    ("estagio_4", estagio_4_elegibilidade(n=5, m=3, frac_cabo=0.4, seed=14)),
]


@pytest.mark.parametrize("nome,inst", CASOS, ids=[c[0] for c in CASOS])
def test_otimo_identico_com_e_sem_mtz(nome: str, inst) -> None:
    com = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=120)
    sem = resolver(inst, ConfigModelo(usar_mtz=False), tempo_limite=120)
    otimo_bruto, _ = forca_bruta(inst)

    assert com.status == "Optimal", f"{nome} com MTZ: {com.mensagem}"
    assert sem.status == "Optimal", f"{nome} sem MTZ: {sem.mensagem}"
    assert com.objetivo == pytest.approx(sem.objetivo, abs=1e-4)
    assert com.objetivo == pytest.approx(otimo_bruto, abs=1e-4)


def test_mtz_acrescenta_restricoes_mas_nao_muda_a_natureza_do_modelo() -> None:
    inst = estagio_4_elegibilidade(n=5, m=3, frac_cabo=0.4, seed=14)
    prob_com, var_com = construir(inst, ConfigModelo(usar_mtz=True))
    prob_sem, var_sem = construir(inst, ConfigModelo(usar_mtz=False))

    assert len(prob_com.constraints) > len(prob_sem.constraints)
    assert len(var_com.y) == len(var_sem.y)  # o grafo de arcos é o mesmo
    assert len(var_com.u) == inst.n and len(var_sem.u) == 0


def test_relaxacao_linear_nao_piora_com_mtz() -> None:
    """O limitante da relaxação com MTZ tem que ser ≥ o de sem MTZ.

    É o efeito que justifica manter restrições redundantes no modelo, e o que o
    experimento MTZ ligado × desligado mede em escala maior.
    """
    import pulp

    inst = estagio_4_elegibilidade(n=5, m=3, frac_cabo=0.4, seed=14)
    limites = []
    for usar_mtz in (False, True):
        prob, _ = construir(inst, ConfigModelo(usar_mtz=usar_mtz))
        for variavel in prob.variables():
            if variavel.cat == pulp.LpBinary:
                variavel.cat = pulp.LpContinuous
                variavel.lowBound, variavel.upBound = 0, 1
        prob.solve(pulp.PULP_CBC_CMD(msg=0))
        limites.append(pulp.value(prob.objective))

    sem_mtz, com_mtz = limites
    assert com_mtz >= sem_mtz - 1e-6
