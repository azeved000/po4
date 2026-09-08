"""Testes do avaliador independente.

Os números aqui são calculados **à mão** no próprio teste, e não gerados por
outra função do projeto. Se `avaliar` for reescrito com um erro de timing, é
este arquivo que precisa acusar.
"""

from __future__ import annotations

import pytest

from rubbertech.dominio import Instancia, InstanciaInvalida, Item, Programacao, Tarefa
from rubbertech.solucao import avaliar, metricas


def instancia_manual() -> Instancia:
    """Três itens, duas linhas; B só roda em L1 e C só em L2."""
    itens = {
        "A": Item(id="A", p={"L1": 10.0, "L2": 12.0}, d=20.0, w=2.0),
        "B": Item(id="B", p={"L1": 8.0}, d=15.0, w=3.0),
        "C": Item(id="C", p={"L2": 6.0}, d=9.0, w=1.0),
    }
    setup = {
        ("INI", "A"): 3.0,
        ("INI", "B"): 5.0,
        ("INI", "C"): 4.0,
        ("A", "B"): 7.0,
        ("B", "A"): 2.0,
        ("A", "C"): 6.0,
        ("C", "A"): 1.0,
    }
    inst = Instancia(itens=itens, linhas=["L1", "L2"], setup=setup)
    inst.validar()
    return inst


def test_avaliar_reproduz_calculo_manual() -> None:
    """L1: A -> B, L2: C.

    L1: setup INI->A = 3  => início 3,  fim 3 + 10 = 13, d = 20 => T = 0
        setup A->B   = 7  => início 20, fim 20 + 8 = 28, d = 15 => T = 13, w = 3
    L2: setup INI->C = 4  => início 4,  fim 4 + 6 = 10,  d = 9  => T = 1,  w = 1
    Objetivo = 3*13 + 1*1 = 40
    """
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})

    tarefa_a = prog.tarefa("A")
    assert (tarefa_a.setup, tarefa_a.inicio, tarefa_a.fim, tarefa_a.atraso) == (
        3.0,
        3.0,
        13.0,
        0.0,
    )
    tarefa_b = prog.tarefa("B")
    assert (tarefa_b.setup, tarefa_b.inicio, tarefa_b.fim, tarefa_b.atraso) == (
        7.0,
        20.0,
        28.0,
        13.0,
    )
    tarefa_c = prog.tarefa("C")
    assert (tarefa_c.setup, tarefa_c.inicio, tarefa_c.fim, tarefa_c.atraso) == (
        4.0,
        4.0,
        10.0,
        1.0,
    )
    assert prog.objetivo == pytest.approx(40.0)


def test_avaliar_usa_o_setup_assimetrico_correto() -> None:
    """Invertendo a ordem em L1, o setup aplicado é s[B,A] = 2, não s[A,B] = 7.

    L1: setup INI->B = 5 => início 5, fim 5 + 8 = 13,  d = 15 => T = 0
        setup B->A   = 2 => início 15, fim 15 + 10 = 25, d = 20 => T = 5, w = 2
    Objetivo = 2*5 = 10 (mais o item C avaliado à parte)
    """
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["B", "A"]})
    assert prog.tarefa("A").setup == 2.0
    assert prog.tarefa("A").fim == pytest.approx(25.0)
    assert prog.objetivo == pytest.approx(10.0)


def test_avaliar_penaliza_antecipacao_quando_alfa_positivo() -> None:
    """Com α = 0,5: só A antecipa (d = 20, C = 13 => A_i = 7 => 3,5)."""
    inst = instancia_manual()
    prog = avaliar(
        inst, {"L1": ["A", "B"], "L2": ["C"]}, penalidade_antecipacao=0.5
    )
    assert prog.objetivo == pytest.approx(40.0 + 3.5)


def test_avaliar_aceita_alfa_por_item() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]}, {"A": 1.0})
    assert prog.objetivo == pytest.approx(40.0 + 7.0)


def test_avaliar_recusa_linha_inelegivel() -> None:
    inst = instancia_manual()
    with pytest.raises(InstanciaInvalida, match="não é elegível"):
        avaliar(inst, {"L2": ["B"]})


def test_avaliar_recusa_linha_e_item_inexistentes() -> None:
    inst = instancia_manual()
    with pytest.raises(KeyError):
        avaliar(inst, {"L9": ["A"]})
    with pytest.raises(KeyError):
        avaliar(inst, {"L1": ["Z"]})


def test_avaliar_completa_linhas_vazias() -> None:
    """Toda linha da instância aparece nas sequências, mesmo sem itens."""
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"]})
    assert prog.sequencias == {"L1": ["A", "B"], "L2": []}


def test_metricas() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})
    m = metricas(prog, inst)
    assert m["atraso_ponderado"] == pytest.approx(40.0)
    assert m["atraso_total"] == pytest.approx(14.0)  # 0 + 13 + 1
    assert m["n_atrasados"] == 2
    assert m["makespan"] == pytest.approx(28.0)
    assert m["tempo_total_setup"] == pytest.approx(14.0)  # 3 + 7 + 4
    ocupacao = m["ocupacao_por_linha"]
    assert ocupacao["L1"] == pytest.approx(1.0)  # (3+10+7+8) / 28
    assert ocupacao["L2"] == pytest.approx(10.0 / 28.0)


def test_metricas_de_programacao_vazia() -> None:
    prog = Programacao(sequencias={"L1": []}, tarefas=[], objetivo=0.0)
    m = metricas(prog)
    assert m["makespan"] == 0.0
    assert m["n_atrasados"] == 0
    assert m["ocupacao_por_linha"] == {"L1": 0.0}


def test_tarefas_da_linha_vem_em_ordem_cronologica() -> None:
    tarefas = [
        Tarefa(item="B", linha="L1", inicio=20.0, fim=28.0, setup=7.0, atraso=13.0),
        Tarefa(item="A", linha="L1", inicio=3.0, fim=13.0, setup=3.0, atraso=0.0),
    ]
    prog = Programacao(sequencias={"L1": ["A", "B"]}, tarefas=tarefas, objetivo=39.0)
    assert [t.item for t in prog.tarefas_da_linha("L1")] == ["A", "B"]
