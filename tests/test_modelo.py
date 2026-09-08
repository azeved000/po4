"""Testes estruturais do MILP: tamanho do modelo e elegibilidade."""

from __future__ import annotations

import pulp
import pytest

from rubbertech.instancias import estagio_4_elegibilidade, instancia_referencia
from rubbertech.modelo import ConfigModelo, construir, tamanho


def test_contagem_de_variaveis_bate_com_os_arcos_validos() -> None:
    inst = instancia_referencia()
    _, var = construir(inst, ConfigModelo(usar_mtz=True))

    n_arcos = sum(1 for _ in inst.arcos())
    n_pares_item_linha = sum(len(inst.elegiveis(i)) for i in inst.J)

    assert len(var.x) == n_pares_item_linha
    assert len(var.y) == n_arcos
    assert len(var.C) == len(var.T) == len(var.A) == inst.n
    assert len(var.u) == inst.n

    # Números concretos da instância de referência: 2 itens presos à L4 (1 linha
    # elegível cada) e 6 itens livres (4 linhas cada) => 2 + 24 = 26.
    assert n_pares_item_linha == 26
    assert n_arcos == 172


def test_contagem_de_restricoes_bate_com_a_formulacao() -> None:
    inst = instancia_referencia()
    n_arcos = sum(1 for _ in inst.arcos())
    n_pares = sum(len(inst.elegiveis(i)) for i in inst.J)
    n_arcos_iniciais = sum(1 for i, _, _ in inst.arcos() if i == inst.no_inicial)

    prob_com, _ = construir(inst, ConfigModelo(usar_mtz=True))
    prob_sem, _ = construir(inst, ConfigModelo(usar_mtz=False))

    # (1) n  +  (2) pares  +  (2') pares  +  (3) m  +  (4)/(4') arcos
    # + (5) n  +  (5') n
    esperado_sem_mtz = inst.n + 2 * n_pares + len(inst.M) + n_arcos + 2 * inst.n
    assert tamanho(prob_sem)[1] == esperado_sem_mtz == 252
    # (6) vale para todo arco cujo predecessor não é o nó fictício.
    assert tamanho(prob_com)[1] == esperado_sem_mtz + (n_arcos - n_arcos_iniciais)
    assert tamanho(prob_com) == (230, 398)


def test_nenhuma_variavel_para_linha_inelegivel() -> None:
    inst = instancia_referencia()
    _, var = construir(inst)

    for i, k in var.x:
        assert k in inst.elegiveis(i)
    for i, j, k in var.y:
        assert k in inst.elegiveis(j)
        assert i == inst.no_inicial or k in inst.elegiveis(i)

    # Concretamente: nada de CA1 ou CA2 fora da L4.
    assert not [(i, k) for (i, k) in var.x if i.startswith("CA") and k != "L4"]
    assert not [
        (i, j, k) for (i, j, k) in var.y if k != "L4" and "CA" in (i[:2], j[:2])
    ]


def test_sem_mtz_nao_cria_variaveis_u() -> None:
    inst = estagio_4_elegibilidade(n=5, m=3, seed=14)
    _, var = construir(inst, ConfigModelo(usar_mtz=False))
    assert var.u == {}
    assert not [v for v in construir(inst, ConfigModelo(usar_mtz=False))[0].variables()
                if v.name.startswith("u_")]


def test_restricoes_tem_nomes_legiveis() -> None:
    """Sem nomes, o .lp exportado vira _C1, _C2... e depurar fica impossível."""
    inst = instancia_referencia()
    prob, _ = construir(inst)
    nomes = set(prob.constraints)
    assert "alocacao_CA1" in nomes
    assert "entrada_TX3_L2" in nomes
    assert "saida_TX3_L2" in nomes
    assert "origem_L4" in nomes
    assert "tempo_inicial_CA1_L4" in nomes
    assert "tempo_TX3_TX4_L1" in nomes
    assert "atraso_TX5" in nomes
    assert "antecipacao_TX5" in nomes
    assert "mtz_TX3_TX4_L1" in nomes
    assert all(not nome.startswith("_C") for nome in nomes)


def test_objetivo_usa_pesos_e_alfa() -> None:
    inst = instancia_referencia()
    prob, var = construir(inst, ConfigModelo(penalidade_antecipacao=0.5))
    coeficientes = prob.objective
    assert coeficientes[var.T["CA1"]] == pytest.approx(8.0)  # w de CA1
    assert coeficientes[var.T["TX5"]] == pytest.approx(1.0)
    assert coeficientes[var.A["TX5"]] == pytest.approx(0.5)


def test_alfa_zero_nao_entra_no_objetivo() -> None:
    inst = instancia_referencia()
    prob, var = construir(inst)
    assert var.A["TX5"] not in prob.objective


def test_big_m_da_configuracao_prevalece() -> None:
    inst = instancia_referencia()
    _, var = construir(inst, ConfigModelo(big_m=999.0))
    assert var.big_m == 999.0
    _, padrao = construir(inst)
    assert padrao.big_m == inst.big_m() == 464.0


def test_modelo_e_de_minimizacao() -> None:
    prob, _ = construir(instancia_referencia())
    assert prob.sense == pulp.LpMinimize
