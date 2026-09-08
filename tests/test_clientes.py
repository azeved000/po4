"""Testes da atribuição de clientes aos pedidos.

O cliente não entra na formulação — o modelo só enxerga ``w``. O que ele muda é
a **estrutura** dos pesos: como a criticidade é propriedade do cliente, pedidos
do mesmo cliente compartilham o peso, e a carteira deixa de ser um conjunto de
atrasos independentes. É isso que estes testes protegem.
"""

from __future__ import annotations

import pytest

from rubbertech.instancias import (
    CLIENTES_PADRAO,
    estagio_6_completo,
    gerar_carteira,
    instancia_referencia,
)
from rubbertech.io_dados import de_dicionario, para_dicionario
from rubbertech.relatorio import formatar_por_cliente, formatar_programacao
from rubbertech.solucao import avaliar
from rubbertech.validacao import forca_bruta

LINHAS = ["L1", "L2", "L3", "L4"]


def test_todo_pedido_tem_cliente() -> None:
    inst = estagio_6_completo(seed=6, n=40)
    assert all(item.cliente for item in inst.itens.values())


def test_clientes_se_repetem_na_carteira() -> None:
    """Com 40 pedidos e ~2,5 por cliente, há bem menos clientes que pedidos."""
    inst = estagio_6_completo(seed=6, n=40)
    clientes = inst.clientes
    assert len(clientes) < inst.n
    assert any(len(pedidos) > 1 for pedidos in clientes.values())


def test_peso_e_propriedade_do_cliente_nao_do_pedido() -> None:
    """Dois pedidos do mesmo cliente têm obrigatoriamente o mesmo peso."""
    inst = estagio_6_completo(seed=6, n=60)
    for cliente, pedidos in inst.clientes.items():
        pesos = {inst.itens[pedido].w for pedido in pedidos}
        assert len(pesos) == 1, f"{cliente} tem pesos diferentes: {pesos}"


def test_peso_vem_do_catalogo_de_clientes() -> None:
    criticidade = dict(CLIENTES_PADRAO)
    inst = estagio_6_completo(seed=6, n=30)
    for item in inst.itens.values():
        assert item.w == criticidade[item.cliente]


def test_numero_de_clientes_acompanha_o_tamanho_da_carteira() -> None:
    pequena = gerar_carteira(4, LINHAS, seed=1)
    grande = gerar_carteira(40, LINHAS, seed=1)
    assert len({i.cliente for i in pequena.values()}) <= len(
        {i.cliente for i in grande.values()}
    )


def test_pesos_explicitos_desligam_o_acoplamento_com_o_cliente() -> None:
    """Passar `pesos` volta ao sorteio por pedido — usado nos casos de borda."""
    itens = gerar_carteira(20, LINHAS, seed=3, pesos=[1.0])
    assert all(item.w == 1.0 for item in itens.values())
    assert all(item.cliente for item in itens.values())


def test_catalogo_de_clientes_tem_criticidade_unica_por_cliente() -> None:
    """Um cliente não pode aparecer duas vezes no catálogo com pesos diferentes."""
    nomes = [nome for nome, _ in CLIENTES_PADRAO]
    assert len(nomes) == len(set(nomes))


# ----------------------------------------------------------------------
# Instância de referência
# ----------------------------------------------------------------------
def test_referencia_mantem_o_otimo_de_144() -> None:
    """Acrescentar clientes é rotulagem: não pode mexer no valor ótimo."""
    inst = instancia_referencia()
    assert forca_bruta(inst)[0] == pytest.approx(144.0)


def test_referencia_respeita_peso_por_cliente() -> None:
    inst = instancia_referencia()
    for pedidos in inst.clientes.values():
        assert len({inst.itens[pedido].w for pedido in pedidos}) == 1
    # Fábio Assunção é o único com dois pedidos, ambos de peso 2.
    assert sorted(inst.clientes["Fábio Assunção"]) == ["CA2", "TX7"]


# ----------------------------------------------------------------------
# Persistência e relatório
# ----------------------------------------------------------------------
def test_cliente_sobrevive_ao_json() -> None:
    inst = instancia_referencia()
    recarregada = de_dicionario(para_dicionario(inst))
    for item_id, item in inst.itens.items():
        assert recarregada.itens[item_id].cliente == item.cliente


def test_json_sem_cliente_continua_valido() -> None:
    """Arquivos antigos, sem o campo, seguem carregando com cliente vazio."""
    dados = para_dicionario(instancia_referencia())
    for bruto in dados["itens"]:
        del bruto["cliente"]
    recarregada = de_dicionario(dados)
    assert all(item.cliente == "" for item in recarregada.itens.values())


def test_relatorio_agrega_atraso_por_cliente() -> None:
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
    texto = formatar_por_cliente(inst, prog)
    assert "ATRASO POR CLIENTE" in texto
    # Fábio Assunção tem 2 pedidos; a linha precisa refletir isso.
    linha = next(l for l in texto.splitlines() if l.startswith("Fábio Assunção"))
    assert " 2 " in linha
    # Mariana Yamamoto (peso 6) é protegida: contribuição zero.
    linha_protegida = next(
        l for l in texto.splitlines() if l.startswith("Mariana Yamamoto")
    )
    assert linha_protegida.rstrip().endswith("0,0")
    # A tabela vem ordenada da maior contribuição para a menor.
    assert texto.index("Adriana Prado") < texto.index("Mariana Yamamoto")


def test_programacao_mostra_coluna_de_cliente() -> None:
    inst = instancia_referencia()
    prog = avaliar(inst, {"L4": ["CA1", "CA2"]})
    texto = formatar_programacao(inst, prog)
    assert "cliente" in texto
    assert "Adriana Prado" in texto


def test_relatorio_omite_cliente_quando_nao_ha() -> None:
    """Instâncias sem cliente não ganham uma coluna vazia."""
    from rubbertech.dominio import Instancia, Item

    itens = {"A": Item(id="A", p={"L1": 5.0}, d=10.0, w=1.0)}
    inst = Instancia(itens=itens, linhas=["L1"], setup={("INI", "A"): 1.0})
    inst.validar()
    texto = formatar_programacao(inst, avaliar(inst, {"L1": ["A"]}))
    assert "cliente" not in texto
    assert "ATRASO POR CLIENTE" not in texto
