"""Testes das entidades e invariantes do domínio."""

from __future__ import annotations

import pytest

from rubbertech.dominio import InstanciaInvalida, Instancia, Item


def _instancia_minima() -> Instancia:
    """Duas linhas, dois itens; um deles restrito à linha L2 (cabo de aço)."""
    itens = {
        "A": Item(id="A", p={"L1": 10.0, "L2": 12.0}, d=20.0, w=2.0),
        "B": Item(id="B", p={"L2": 8.0}, d=15.0, w=1.0, cabo_aco=True),
    }
    setup = {
        ("INI", "A"): 3.0,
        ("INI", "B"): 5.0,
        ("A", "B"): 7.0,
        ("B", "A"): 2.0,
    }
    return Instancia(itens=itens, linhas=["L1", "L2"], setup=setup)


# ----------------------------------------------------------------------
# Conjuntos e estrutura
# ----------------------------------------------------------------------
def test_conjuntos_basicos() -> None:
    inst = _instancia_minima()
    assert inst.J == ["A", "B"]
    assert inst.J0 == ["INI", "A", "B"]
    assert inst.M == ["L1", "L2"]
    assert inst.n == 2
    assert inst.elegiveis("B") == ("L2",)


def test_arcos_respeitam_elegibilidade() -> None:
    """Nenhum arco pode envolver a linha L1 para o item B (só elegível em L2)."""
    inst = _instancia_minima()
    arcos = list(inst.arcos())
    assert all(not (j == "B" and k == "L1") for _, j, k in arcos)
    assert all(not (i == "B" and k == "L1") for i, _, k in arcos)
    # Em L1 só cabe o arco INI->A; em L2 cabem INI->A, INI->B, A->B, B->A.
    assert set(arcos) == {
        ("INI", "A", "L1"),
        ("INI", "A", "L2"),
        ("INI", "B", "L2"),
        ("A", "B", "L2"),
        ("B", "A", "L2"),
    }


def test_arcos_nao_incluem_lacos() -> None:
    inst = _instancia_minima()
    assert all(i != j for i, j, _ in inst.arcos())


# ----------------------------------------------------------------------
# Big-M
# ----------------------------------------------------------------------
def test_big_m_positivo_e_maior_que_qualquer_conclusao() -> None:
    """V deve dominar a pior conclusão concebível: tudo em série na pior linha."""
    inst = _instancia_minima()
    valor = inst.big_m()
    assert valor > 0
    # V = (p_max[A] + s_max[·,A]) + (p_max[B] + s_max[·,B]) + max(d)
    #   = (12 + 3) + (8 + 7) + 20 = 50
    assert valor == pytest.approx(50.0)
    # Pior conclusão concebível: tudo em série, sempre com o pior tempo e o
    # pior setup de entrada de cada item.
    pior_conclusao = sum(
        max(item.p.values())
        + max(v for (o, dst), v in inst.setup.items() if dst == nome and o != nome)
        for nome, item in inst.itens.items()
    )
    assert valor >= pior_conclusao
    assert valor >= max(item.d for item in inst.itens.values())


def test_big_m_cresce_com_a_instancia() -> None:
    inst = _instancia_minima()
    antes = inst.big_m()
    inst.itens["C"] = Item(id="C", p={"L1": 30.0}, d=100.0, w=1.0)
    inst.setup[("INI", "C")] = 4.0
    inst.setup[("A", "C")] = 6.0
    inst.setup[("C", "A")] = 6.0
    assert inst.big_m() > antes


# ----------------------------------------------------------------------
# Validação
# ----------------------------------------------------------------------
def test_validar_aceita_instancia_correta() -> None:
    _instancia_minima().validar()  # não deve levantar


def test_rejeita_item_sem_linha_elegivel() -> None:
    inst = _instancia_minima()
    inst.itens["C"] = Item(id="C", p={}, d=10.0, w=1.0)
    with pytest.raises(InstanciaInvalida, match="C.*linha elegível"):
        inst.validar()


def test_rejeita_tempo_de_processamento_ausente_ou_invalido() -> None:
    """`p` nulo ou não-positivo é tratado como 'faltando p[i,k]'."""
    inst = _instancia_minima()
    inst.itens["A"].p["L1"] = 0.0
    with pytest.raises(InstanciaInvalida, match=r"\('A', 'L1'\)"):
        inst.validar()


def test_rejeita_linha_inexistente_em_p() -> None:
    inst = _instancia_minima()
    inst.itens["A"].p["L9"] = 5.0
    with pytest.raises(InstanciaInvalida, match="L9"):
        inst.validar()


def test_rejeita_setup_ausente() -> None:
    inst = _instancia_minima()
    del inst.setup[("A", "B")]
    with pytest.raises(InstanciaInvalida, match=r"Setup ausente.*'A'.*'B'"):
        inst.validar()


def test_rejeita_setup_negativo() -> None:
    inst = _instancia_minima()
    inst.setup[("A", "B")] = -1.0
    with pytest.raises(InstanciaInvalida, match=r"Setup inválido"):
        inst.validar()


def test_rejeita_prazo_negativo() -> None:
    inst = _instancia_minima()
    inst.itens["A"] = Item(id="A", p={"L1": 10.0}, d=-1.0, w=2.0)
    with pytest.raises(InstanciaInvalida, match="prazo negativo"):
        inst.validar()


def test_rejeita_peso_negativo() -> None:
    inst = _instancia_minima()
    inst.itens["A"] = Item(id="A", p={"L1": 10.0}, d=5.0, w=-2.0)
    with pytest.raises(InstanciaInvalida, match="peso negativo"):
        inst.validar()


def test_rejeita_no_inicial_colidindo_com_item() -> None:
    inst = _instancia_minima()
    inst.no_inicial = "A"
    with pytest.raises(InstanciaInvalida, match="colide"):
        inst.validar()


def test_tempo_em_linha_inelegivel_levanta_erro() -> None:
    inst = _instancia_minima()
    with pytest.raises(InstanciaInvalida, match="não é elegível"):
        inst.p("B", "L1")
