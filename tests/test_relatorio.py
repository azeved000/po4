"""Testes da saída textual.

O relatório é o que o leitor do trabalho realmente vê. O ponto crítico não é a
estética: é não apresentar uma solução meramente viável como se fosse o ótimo, e
não anunciar um gap que não foi demonstrado.
"""

from __future__ import annotations

from rubbertech.instancias import instancia_referencia
from rubbertech.relatorio import (
    formatar_instancia,
    formatar_programacao,
    formatar_resultado,
    formatar_violacoes,
    tabela_comparativa,
)
from rubbertech.solucao import avaliar
from rubbertech.solver import Resultado

PROGRAMACAO_OTIMA = {
    "L1": ["TX4", "TX3"],
    "L2": ["TX6", "TX7"],
    "L3": ["TX8", "TX5"],
    "L4": ["CA1", "CA2"],
}


def _resultado(**ajustes) -> Resultado:
    padrao = dict(
        status="Optimal",
        objetivo=144.0,
        limite_inferior=144.0,
        gap=0.0,
        tempo_s=13.47,
        n_variaveis=230,
        n_restricoes=398,
        programacao=None,
        divergencia_recalculo=0.0,
        mensagem="Optimal solution found",
    )
    padrao.update(ajustes)
    return Resultado(**padrao)


def test_otimo_provado_e_anunciado_como_tal() -> None:
    texto = formatar_resultado(_resultado())
    assert "ótimo provado" in texto
    assert "0,00%" in texto
    assert "ATENÇÃO" not in texto


def test_solucao_viavel_nao_e_anunciada_como_otima() -> None:
    """O aviso é obrigatório: sem ele o relatório mentiria por omissão."""
    texto = formatar_resultado(
        _resultado(
            status="Not Solved",
            objetivo=932.2,
            limite_inferior=250.0,
            gap=2.73,
            mensagem="Stopped on time limit",
        )
    )
    assert "NÃO é o ótimo provado" in texto
    assert "limitante superior" in texto
    assert "273,00%" in texto


def test_gap_indefinido_quando_o_limite_inferior_e_nulo() -> None:
    texto = formatar_resultado(
        _resultado(
            status="Not Solved",
            objetivo=7599.6,
            limite_inferior=0.0,
            gap=None,
            mensagem="Stopped on time limit",
        )
    )
    assert "indefinido (limite inferior nulo)" in texto
    assert "não há como afirmar quão longe do" in texto
    # Separador de milhar no padrão brasileiro.
    assert "7.599,60" in texto


def test_inviavel_nao_mostra_objetivo() -> None:
    texto = formatar_resultado(
        _resultado(
            status="Infeasible", objetivo=None, limite_inferior=None, gap=None
        )
    )
    assert "inviável" in texto
    assert "objetivo ............ -" in texto


def test_programacao_marca_itens_atrasados() -> None:
    inst = instancia_referencia()
    prog = avaliar(inst, PROGRAMACAO_OTIMA)
    texto = formatar_programacao(inst, prog)

    assert "Linha L1: TX4 -> TX3" in texto
    assert "Linha L4: CA1 -> CA2" in texto
    # TX5 atrasa 25 u.t.; TX6 termina no prazo.
    linha_tx5 = next(l for l in texto.splitlines() if l.strip().startswith("2  TX5"))
    assert "ATRASO" in linha_tx5
    linha_tx6 = next(l for l in texto.splitlines() if l.strip().startswith("1  TX6"))
    assert "no prazo" in linha_tx6
    assert "atraso ponderado (objetivo) . 144,00" in texto


def test_formatacao_e_ascii_pura_na_moldura() -> None:
    """A moldura não pode usar traços de caixa: o console cp1252 não os codifica."""
    inst = instancia_referencia()
    texto = formatar_programacao(inst, avaliar(inst, PROGRAMACAO_OTIMA))
    texto += formatar_instancia(inst) + formatar_resultado(_resultado())
    proibidos = "─│┌┐└┘├┤┬┴┼━┃✓✗"
    assert not [c for c in proibidos if c in texto]
    texto.encode("cp1252")  # não pode levantar UnicodeEncodeError


def test_violacoes() -> None:
    assert "nenhuma violação" in formatar_violacoes([])
    texto = formatar_violacoes(["item duplicado", "linha inelegível"])
    assert "2 violação(ões)" in texto
    assert "- item duplicado" in texto


def test_tabela_comparativa() -> None:
    texto = tabela_comparativa(
        {
            "com MTZ": _resultado(),
            "sem MTZ": _resultado(
                status="Not Solved", limite_inferior=48.0, gap=2.0, n_restricoes=252
            ),
        }
    )
    assert "com MTZ" in texto and "sem MTZ" in texto
    assert "Optimal" in texto and "Not Solved" in texto
