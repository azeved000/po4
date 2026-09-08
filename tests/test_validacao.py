"""Testes do verificador independente e da enumeração exaustiva."""

from __future__ import annotations

import itertools
import math

import pytest

from rubbertech.dominio import Programacao, Tarefa
from rubbertech.solucao import avaliar
from rubbertech.validacao import forca_bruta, verificar
from tests.test_solucao import instancia_manual


# ----------------------------------------------------------------------
# verificar
# ----------------------------------------------------------------------
def test_programacao_correta_nao_tem_violacoes() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})
    assert verificar(inst, prog) == []


def test_detecta_item_duplicado_e_ausente() -> None:
    """A aparece em duas linhas e B em nenhuma."""
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A"], "L2": ["A", "C"]})
    violacoes = verificar(inst, prog)
    assert any("'A' aparece 2 vezes" in v for v in violacoes)
    assert any("'B' não aparece" in v for v in violacoes)


def test_detecta_item_em_linha_inelegivel() -> None:
    """`avaliar` recusaria isso, então a programação é montada à mão."""
    inst = instancia_manual()
    tarefas = [
        Tarefa(item="A", linha="L1", inicio=3.0, fim=13.0, setup=3.0, atraso=0.0),
        Tarefa(item="C", linha="L1", inicio=19.0, fim=25.0, setup=6.0, atraso=16.0),
        Tarefa(item="B", linha="L2", inicio=5.0, fim=13.0, setup=5.0, atraso=0.0),
    ]
    prog = Programacao(
        sequencias={"L1": ["A", "C"], "L2": ["B"]}, tarefas=tarefas, objetivo=16.0
    )
    violacoes = verificar(inst, prog)
    assert any("'B' foi alocado à linha 'L2'" in v for v in violacoes)


def test_detecta_objetivo_adulterado() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})
    prog.objetivo = 1.0
    violacoes = verificar(inst, prog)
    assert len(violacoes) == 1
    assert "difere do recalculado" in violacoes[0]


def test_detecta_sobreposicao_temporal() -> None:
    """B começa antes de A terminar: a linha estaria produzindo dois itens."""
    inst = instancia_manual()
    tarefas = [
        Tarefa(item="A", linha="L1", inicio=3.0, fim=13.0, setup=3.0, atraso=0.0),
        Tarefa(item="B", linha="L1", inicio=10.0, fim=18.0, setup=7.0, atraso=3.0),
    ]
    prog = Programacao(sequencias={"L1": ["A", "B"]}, tarefas=tarefas, objetivo=9.0)
    assert any("Sobreposição na linha 'L1'" in v for v in verificar(inst, prog))


def test_detecta_setup_incorreto() -> None:
    """Aplicar s[A,B] = 7 quando o par real exige s[B,A] = 2 (assimetria)."""
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["B", "A"], "L2": ["C"]})
    tarefa_a = prog.tarefa("A")
    tarefa_a.setup = 7.0  # o valor do par invertido
    violacoes = verificar(inst, prog)
    assert any("Setup incorreto antes de 'A'" in v for v in violacoes)


def test_detecta_duracao_e_atraso_incorretos() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A"], "L2": ["C"]})
    prog.tarefa("A").fim = 99.0
    violacoes = verificar(inst, prog)
    assert any("Duração incorreta" in v for v in violacoes)
    assert any("Atraso incorreto" in v for v in violacoes)


def test_detecta_linha_inexistente() -> None:
    inst = instancia_manual()
    prog = Programacao(sequencias={"L9": ["A"]}, tarefas=[], objetivo=0.0)
    assert any("Linha 'L9' não existe" in v for v in verificar(inst, prog))


# ----------------------------------------------------------------------
# forca_bruta
# ----------------------------------------------------------------------
def enumeracao_ingenua(inst, alfa: float = 0.0) -> float:
    """Enumeração alternativa, escrita de forma diferente de `forca_bruta`.

    Percorre todas as atribuições item→linha com `itertools.product` e todas as
    permutações de cada grupo com `itertools.permutations`, sem poda nenhuma.
    Serve de terceira opinião: se as duas concordam, o erro teria que estar nas
    duas ao mesmo tempo.
    """
    itens = inst.J
    opcoes = [inst.elegiveis(i) for i in itens]
    melhor = math.inf
    for atribuicao in itertools.product(*opcoes):
        grupos: dict[str, list[str]] = {linha: [] for linha in inst.M}
        for item_id, linha in zip(itens, atribuicao, strict=True):
            grupos[linha].append(item_id)
        permutacoes_por_linha = [
            list(itertools.permutations(grupos[linha])) for linha in inst.M
        ]
        for combinacao in itertools.product(*permutacoes_por_linha):
            sequencias = {
                linha: list(perm)
                for linha, perm in zip(inst.M, combinacao, strict=True)
            }
            melhor = min(melhor, avaliar(inst, sequencias, alfa).objetivo)
    return melhor


def test_forca_bruta_bate_com_enumeracao_ingenua() -> None:
    inst = instancia_manual()
    custo, prog = forca_bruta(inst)
    assert custo == pytest.approx(enumeracao_ingenua(inst))
    assert prog.objetivo == pytest.approx(custo)
    assert verificar(inst, prog) == []


def test_forca_bruta_com_penalidade_de_antecipacao() -> None:
    inst = instancia_manual()
    custo, _ = forca_bruta(inst, penalidade_antecipacao=0.5)
    assert custo == pytest.approx(enumeracao_ingenua(inst, 0.5))


def test_forca_bruta_respeita_elegibilidade() -> None:
    inst = instancia_manual()
    _, prog = forca_bruta(inst)
    assert "B" not in prog.sequencias["L2"]
    assert "C" not in prog.sequencias["L1"]


def test_forca_bruta_recusa_instancia_grande() -> None:
    inst = instancia_manual()
    with pytest.raises(ValueError, match="recusada"):
        forca_bruta(inst, max_itens=2)
