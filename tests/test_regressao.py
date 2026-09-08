"""Testes de regressão: o modelo tem que reproduzir resultados já conhecidos.

São dois tipos de âncora:

* a instância de referência, cujo ótimo (``Z = 144,0``) foi verificado por
  enumeração exaustiva e está documentado no relatório;
* instâncias pequenas com seeds fixas, em que o ótimo do solver é confrontado
  com o da força bruta.

Se um destes falhar, o problema é no modelo — não se ajusta a instância para o
teste passar.
"""

from __future__ import annotations

import pytest

from rubbertech.instancias import (
    OTIMO_REFERENCIA,
    estagio_1_maquina_unica,
    estagio_2_setup,
    estagio_3_subciclos,
    estagio_4_elegibilidade,
    instancia_referencia,
)
from rubbertech.modelo import ConfigModelo
from rubbertech.solucao import avaliar
from rubbertech.solver import resolver
from rubbertech.validacao import forca_bruta, verificar

#: Instâncias pequenas (n ≤ 8) com seeds fixas, uma por estágio.
CASOS_PEQUENOS = [
    ("estagio_1", estagio_1_maquina_unica(n=4, seed=11)),
    ("estagio_2", estagio_2_setup(n=4, seed=12)),
    ("estagio_3", estagio_3_subciclos(n=4, seed=13)),
    ("estagio_4", estagio_4_elegibilidade(n=5, m=3, frac_cabo=0.4, seed=14)),
]


def test_forca_bruta_confirma_o_otimo_da_referencia() -> None:
    """A âncora de tudo: 144,0 por enumeração exaustiva, sem solver nenhum."""
    inst = instancia_referencia()
    custo, prog = forca_bruta(inst)
    assert custo == pytest.approx(OTIMO_REFERENCIA)
    assert verificar(inst, prog) == []


def test_programacao_documentada_vale_exatamente_144() -> None:
    """A programação publicada no relatório tem que custar 144,0.

    L1: TX4→TX3 | L2: TX6→TX7 | L3: TX8→TX5 | L4: CA1→CA2
    """
    inst = instancia_referencia()
    prog = avaliar(
        inst,
        {
            "L1": ["TX4", "TX3"],
            "L2": ["TX6", "TX7"],
            "L3": ["TX8", "TX5"],
            "L4": ["CA1", "CA2"],
        },
    )
    assert prog.objetivo == pytest.approx(144.0)
    assert verificar(inst, prog) == []


def test_o_otimo_sacrifica_o_item_barato() -> None:
    """TX5 (peso 1) atrasa 25 u.t. enquanto TX6 (peso 6) e TX4 (peso 3) não.

    É a evidência de que o objetivo pondera por criticidade de cliente. Uma
    implementação que espalhasse o atraso igualmente estaria minimizando o
    atraso total, não o atraso *ponderado*.
    """
    inst = instancia_referencia()
    prog = avaliar(
        inst,
        {
            "L1": ["TX4", "TX3"],
            "L2": ["TX6", "TX7"],
            "L3": ["TX8", "TX5"],
            "L4": ["CA1", "CA2"],
        },
    )
    assert prog.tarefa("TX5").atraso == pytest.approx(25.0)
    assert prog.tarefa("TX6").atraso == pytest.approx(0.0)
    assert prog.tarefa("TX4").atraso == pytest.approx(0.0)


@pytest.mark.lento
def test_modelo_atinge_o_otimo_da_referencia() -> None:
    inst = instancia_referencia()
    res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=300)
    assert res.status == "Optimal"
    assert res.objetivo == pytest.approx(OTIMO_REFERENCIA)
    assert res.programacao is not None
    # O objetivo recalculado de forma independente tem que bater com o do solver.
    assert res.programacao.objetivo == pytest.approx(OTIMO_REFERENCIA)
    assert res.divergencia_recalculo == pytest.approx(0.0, abs=1e-6)
    assert verificar(inst, res.programacao) == []
    # O item de peso 8 (CA1) precisa estar na única linha elegível.
    assert res.programacao.sequencias["L4"][0] == "CA1"


@pytest.mark.parametrize("nome,inst", CASOS_PEQUENOS, ids=[c[0] for c in CASOS_PEQUENOS])
def test_modelo_bate_com_forca_bruta(nome: str, inst) -> None:
    otimo_bruto, _ = forca_bruta(inst)
    res = resolver(inst, tempo_limite=120)
    assert res.status == "Optimal", f"{nome}: {res.mensagem}"
    assert res.objetivo == pytest.approx(otimo_bruto, abs=1e-4)
    assert res.programacao is not None
    assert res.programacao.objetivo == pytest.approx(otimo_bruto, abs=1e-4)
    assert verificar(inst, res.programacao) == []


def test_estagio_3_nao_produz_subciclo() -> None:
    """A armadilha do estágio 3: setup inicial caro e trocas de graça.

    Um modelo sem eliminação de subciclos fecharia um ciclo entre os itens para
    não pagar o setup inicial. `extrair` levantaria erro nesse caso — chegar
    até aqui com todos os itens sequenciados já é o teste.
    """
    inst = estagio_3_subciclos(n=4, seed=13)
    res = resolver(inst, tempo_limite=120)
    assert res.programacao is not None
    sequenciados = [i for seq in res.programacao.sequencias.values() for i in seq]
    assert sorted(sequenciados) == sorted(inst.J)
