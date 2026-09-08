"""REGRAS DE DESPACHO — **NÃO SÃO O MÉTODO DE SOLUÇÃO DESTE TRABALHO**.

ATENÇÃO, EM LETRAS GARRAFAIS, PORQUE ISSO JÁ FOI CONFUNDIDO ANTES:

    AS REGRAS DESTE MÓDULO (EDD, SPT, WSPT) EXISTEM APENAS PARA QUANTIFICAR,
    NO RELATÓRIO, O GANHO OBTIDO PELO MODELO EXATO. ELAS NÃO RESOLVEM O
    PROBLEMA DO TRABALHO. A RESTRIÇÃO METODOLÓGICA DA DISCIPLINA É RÍGIDA: A
    SOLUÇÃO ENTREGUE DEVE SER OBTIDA POR PROGRAMAÇÃO LINEAR INTEIRA MISTA.

Nenhuma função daqui é chamada por :mod:`rubbertech.modelo`, por
:mod:`rubbertech.solver` ou pelo CLI de resolução. Elas aparecem apenas em
``scripts/experimentos.py``, na coluna de comparação.

Uma observação técnica que o relatório deve registrar: as três regras são
míopes quanto ao setup dependente da sequência. Elas ordenam por um atributo do
item (prazo, tempo, razão tempo/peso) e depois despacham para a linha que
termina primeiro. Nenhuma delas antecipa que agrupar itens da mesma família
economiza preparação — que é exatamente a decisão que o modelo exato toma.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from rubbertech.dominio import Instancia, Item, Programacao
from rubbertech.solucao import avaliar


def _despachar(
    inst: Instancia,
    chave: Callable[[Item], float],
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
) -> Programacao:
    """Despacho por lista: ordena os itens por ``chave`` e aloca um a um.

    Cada item vai para a linha elegível em que **terminaria mais cedo**, dado o
    que já foi programado nela (incluindo o setup do par consecutivo real). É a
    extensão usual das regras de fila única para máquinas paralelas.

    O objetivo é sempre recalculado por :func:`rubbertech.solucao.avaliar`, de
    modo que a comparação com o modelo exato use exatamente a mesma conta.
    """
    sequencias: dict[str, list[str]] = {linha: [] for linha in inst.linhas}
    relogio: dict[str, float] = {linha: 0.0 for linha in inst.linhas}
    ultimo: dict[str, str] = {linha: inst.no_inicial for linha in inst.linhas}

    for item in sorted(inst.itens.values(), key=chave):
        melhor_linha = None
        melhor_fim = float("inf")
        for linha in inst.elegiveis(item.id):
            fim = (
                relogio[linha]
                + inst.s(ultimo[linha], item.id)
                + inst.p(item.id, linha)
            )
            if fim < melhor_fim:
                melhor_linha, melhor_fim = linha, fim
        assert melhor_linha is not None  # validar() garante ao menos uma linha
        sequencias[melhor_linha].append(item.id)
        relogio[melhor_linha] = melhor_fim
        ultimo[melhor_linha] = item.id

    return avaliar(inst, sequencias, penalidade_antecipacao)


def edd(
    inst: Instancia, penalidade_antecipacao: float | Mapping[str, float] = 0.0
) -> Programacao:
    """EDD — *earliest due date*: menor prazo primeiro.

    Ótima para minimizar o atraso **máximo** em uma máquina; ignora pesos e
    tempos, então costuma ser cara quando as multas são muito desiguais.
    """
    return _despachar(inst, lambda item: item.d, penalidade_antecipacao)


def spt(
    inst: Instancia, penalidade_antecipacao: float | Mapping[str, float] = 0.0
) -> Programacao:
    """SPT — *shortest processing time*: menor tempo de processamento primeiro.

    Usa o menor tempo entre as linhas elegíveis do item. Minimiza o fluxo médio,
    mas não enxerga prazo nenhum.
    """
    return _despachar(
        inst, lambda item: min(item.p.values()), penalidade_antecipacao
    )


def wspt(
    inst: Instancia, penalidade_antecipacao: float | Mapping[str, float] = 0.0
) -> Programacao:
    """WSPT — regra de Smith: menor razão ``p/w`` primeiro.

    Prioriza item barato de fazer e caro de atrasar. É a melhor das três aqui
    porque é a única que olha para os pesos, e por isso é a comparação mais
    honesta contra o modelo exato.
    """
    return _despachar(
        inst,
        lambda item: min(item.p.values()) / item.w if item.w > 0 else float("inf"),
        penalidade_antecipacao,
    )


#: Regras expostas aos scripts de experimento, por nome.
REGRAS: dict[str, Callable[..., Programacao]] = {
    "EDD": edd,
    "SPT": spt,
    "WSPT": wspt,
}
