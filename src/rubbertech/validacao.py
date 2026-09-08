"""Verificação independente de programações e enumeração exaustiva.

Nada aqui usa o solver para julgar o solver. :func:`verificar` refaz as contas a
partir da instância; :func:`forca_bruta` encontra o ótimo por enumeração
completa em instâncias pequenas. Juntas, elas são a única evidência de que o
modelo PLI está certo — um modelo com erro de sinal, big-M curto ou setup
trocado continua devolvendo "Optimal" com toda a confiança do mundo.

Dependências em tempo de execução: :mod:`rubbertech.dominio` e
:mod:`rubbertech.solucao`. :func:`comparar` precisa do solver, mas o importa
dentro da função, de propósito: assim o verificador continua carregável (e
utilizável) mesmo em um ambiente sem PuLP instalado.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping

from rubbertech.dominio import Instancia, Programacao
from rubbertech.solucao import TOLERANCIA, alfa_de, avaliar

#: Limite acima do qual a enumeração exaustiva é recusada (ver `forca_bruta`).
MAX_ITENS_FORCA_BRUTA = 8


def verificar(
    inst: Instancia,
    prog: Programacao,
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
    tolerancia: float = TOLERANCIA,
) -> list[str]:
    """Devolve a lista de violações de uma programação (vazia = programação sã).

    Retornar uma lista em vez de levantar exceção é proposital: quando algo dá
    errado, interessa ver *todos* os defeitos de uma vez, e não o primeiro.

    Verifica: cobertura (cada item exatamente uma vez), elegibilidade de linha,
    ausência de sobreposição temporal na mesma linha, coerência entre os setups
    aplicados e os pares consecutivos reais, duração das tarefas, cálculo do
    atraso e, por fim, se o objetivo declarado bate com o recalculado.
    """
    violacoes: list[str] = []

    # ---- cobertura: todo item exatamente uma vez ---------------------
    ocorrencias = Counter(
        item for sequencia in prog.sequencias.values() for item in sequencia
    )
    for item_id in inst.J:
        quantas = ocorrencias.get(item_id, 0)
        if quantas == 0:
            violacoes.append(f"Item '{item_id}' não aparece em nenhuma linha.")
        elif quantas > 1:
            violacoes.append(
                f"Item '{item_id}' aparece {quantas} vezes na programação "
                "(deveria aparecer exatamente uma)."
            )
    for item_id in ocorrencias:
        if item_id not in inst.itens:
            violacoes.append(
                f"Item '{item_id}' está na programação mas não existe na instância."
            )

    # ---- linhas e elegibilidade --------------------------------------
    for linha, sequencia in prog.sequencias.items():
        if linha not in inst.linhas:
            violacoes.append(f"Linha '{linha}' não existe na instância.")
            continue
        for item_id in sequencia:
            if item_id in inst.itens and linha not in inst.elegiveis(item_id):
                violacoes.append(
                    f"Item '{item_id}' foi alocado à linha '{linha}', que não é "
                    f"elegível (elegíveis: {list(inst.elegiveis(item_id))})."
                )

    # ---- coerência entre `sequencias` e `tarefas` ---------------------
    for linha, sequencia in prog.sequencias.items():
        cronologica = [t.item for t in prog.tarefas_da_linha(linha)]
        if cronologica != list(sequencia):
            violacoes.append(
                f"Na linha '{linha}', a ordem cronológica das tarefas "
                f"{cronologica} não corresponde à sequência declarada "
                f"{list(sequencia)}."
            )
    linhas_das_tarefas = {t.linha for t in prog.tarefas}
    for linha in linhas_das_tarefas - set(prog.sequencias):
        violacoes.append(
            f"Há tarefas na linha '{linha}', que não consta das sequências."
        )

    # ---- tempos, setups e atrasos ------------------------------------
    for linha in prog.sequencias:
        if linha not in inst.linhas:
            continue
        anterior = inst.no_inicial
        fim_anterior = 0.0
        for tarefa in prog.tarefas_da_linha(linha):
            item_id = tarefa.item
            if item_id not in inst.itens:
                continue
            item = inst.itens[item_id]

            if (i_setup := (anterior, item_id)) in inst.setup:
                esperado = inst.setup[i_setup]
                if abs(tarefa.setup - esperado) > tolerancia:
                    violacoes.append(
                        f"Setup incorreto antes de '{item_id}' na linha "
                        f"'{linha}': aplicado {tarefa.setup}, esperado "
                        f"s['{anterior}','{item_id}'] = {esperado}."
                    )
            else:
                violacoes.append(
                    f"Não há setup definido para o par consecutivo "
                    f"('{anterior}', '{item_id}') usado na linha '{linha}'."
                )

            if tarefa.inicio - tarefa.setup < fim_anterior - tolerancia:
                violacoes.append(
                    f"Sobreposição na linha '{linha}': '{item_id}' começa o setup "
                    f"em {tarefa.inicio - tarefa.setup} mas a tarefa anterior "
                    f"termina em {fim_anterior}."
                )

            if linha in inst.elegiveis(item_id):
                duracao_esperada = inst.p(item_id, linha)
                if abs((tarefa.fim - tarefa.inicio) - duracao_esperada) > tolerancia:
                    violacoes.append(
                        f"Duração incorreta de '{item_id}' na linha '{linha}': "
                        f"{tarefa.fim - tarefa.inicio}, esperado "
                        f"p['{item_id}','{linha}'] = {duracao_esperada}."
                    )

            atraso_esperado = max(0.0, tarefa.fim - item.d)
            if abs(tarefa.atraso - atraso_esperado) > tolerancia:
                violacoes.append(
                    f"Atraso incorreto de '{item_id}': declarado {tarefa.atraso}, "
                    f"esperado max(0, {tarefa.fim} - {item.d}) = {atraso_esperado}."
                )

            fim_anterior = tarefa.fim
            anterior = item_id

    # ---- objetivo declarado x recalculado -----------------------------
    try:
        recalculada = avaliar(inst, prog.sequencias, penalidade_antecipacao)
    except (KeyError, ValueError) as erro:
        violacoes.append(f"Não foi possível recalcular o objetivo: {erro}")
    else:
        if abs(recalculada.objetivo - prog.objetivo) > tolerancia:
            violacoes.append(
                f"Objetivo declarado ({prog.objetivo}) difere do recalculado "
                f"({recalculada.objetivo})."
            )

    return violacoes


def forca_bruta(
    inst: Instancia,
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
    max_itens: int = MAX_ITENS_FORCA_BRUTA,
) -> tuple[float, Programacao]:
    """Encontra o ótimo por enumeração completa. Só para instâncias pequenas.

    Enumera toda atribuição item→linha e toda permutação dentro de cada linha,
    percorrendo as linhas em ordem: em cada nó da busca, ou se acrescenta um
    item ao final da linha corrente, ou se fecha a linha e passa para a
    seguinte. Assim cada programação distinta é gerada exatamente uma vez.

    A poda é a mais simples possível — como todo item só acrescenta custo não
    negativo, um prefixo que já custa mais do que a melhor solução conhecida não
    pode levar a nada melhor. É o suficiente para 8 itens e mantém o código
    obviamente correto, que é o requisito aqui: esta função é a régua contra a
    qual o modelo PLI é medido, então ela não pode ser esperta.

    Levanta ``ValueError`` acima de ``max_itens`` itens — a explosão é
    fatorial e um engano custaria horas de espera silenciosa.
    """
    if inst.n > max_itens:
        raise ValueError(
            f"A enumeração exaustiva foi recusada: a instância tem {inst.n} itens "
            f"e o limite é {max_itens}. O custo cresce fatorialmente."
        )
    inst.validar()

    linhas = inst.M
    ordem = inst.J
    sequencias: dict[str, list[str]] = {linha: [] for linha in linhas}
    melhor_custo = math.inf
    melhor_sequencias: dict[str, list[str]] | None = None

    def expandir(
        indice_linha: int,
        anterior: str,
        relogio: float,
        restantes: frozenset[str],
        acumulado: float,
    ) -> None:
        nonlocal melhor_custo, melhor_sequencias

        if acumulado >= melhor_custo:  # poda
            return

        linha = linhas[indice_linha]
        ultima_linha = indice_linha == len(linhas) - 1

        # Ramo 1: encerrar esta linha.
        if ultima_linha:
            if not restantes:
                melhor_custo = acumulado
                melhor_sequencias = {k: list(v) for k, v in sequencias.items()}
        else:
            expandir(indice_linha + 1, inst.no_inicial, 0.0, restantes, acumulado)

        # Ramo 2: acrescentar mais um item ao final desta linha.
        for item_id in ordem:
            if item_id not in restantes or linha not in inst.elegiveis(item_id):
                continue
            item = inst.itens[item_id]
            fim = relogio + inst.s(anterior, item_id) + inst.p(item_id, linha)
            custo = item.w * max(0.0, fim - item.d) + alfa_de(
                penalidade_antecipacao, item_id
            ) * max(0.0, item.d - fim)
            sequencias[linha].append(item_id)
            expandir(
                indice_linha,
                item_id,
                fim,
                restantes - {item_id},
                acumulado + custo,
            )
            sequencias[linha].pop()

    expandir(0, inst.no_inicial, 0.0, frozenset(ordem), 0.0)

    if melhor_sequencias is None:
        raise ValueError(
            "A enumeração exaustiva não encontrou nenhuma programação viável; "
            "verifique a elegibilidade dos itens."
        )
    return melhor_custo, avaliar(inst, melhor_sequencias, penalidade_antecipacao)


def comparar(
    inst: Instancia,
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
    tempo_limite: int = 300,
    tolerancia: float = 1e-4,
) -> dict[str, object]:
    """Roda modelo PLI e força bruta na mesma instância e confronta os dois.

    A tolerância é folgada (``1e-4``) porque o CBC devolve valores com erro
    numérico de arredondamento; o que se quer detectar aqui é discrepância
    estrutural, não o último bit.
    """
    from rubbertech.modelo import ConfigModelo  # import tardio: ver docstring
    from rubbertech.solver import resolver

    cfg = ConfigModelo(penalidade_antecipacao=penalidade_antecipacao)
    resultado = resolver(inst, cfg, tempo_limite=tempo_limite)
    custo_bruto, prog_bruta = forca_bruta(inst, penalidade_antecipacao)

    objetivo_modelo = (
        resultado.programacao.objetivo if resultado.programacao is not None else None
    )
    coincidem = (
        objetivo_modelo is not None
        and abs(objetivo_modelo - custo_bruto) <= tolerancia
    )
    violacoes = (
        verificar(inst, resultado.programacao, penalidade_antecipacao)
        if resultado.programacao is not None
        else ["O solver não devolveu programação."]
    )

    return {
        "status": resultado.status,
        "objetivo_modelo": objetivo_modelo,
        "objetivo_forca_bruta": custo_bruto,
        "diferenca": (
            None if objetivo_modelo is None else objetivo_modelo - custo_bruto
        ),
        "coincidem": coincidem,
        "violacoes": violacoes,
        "tempo_s": resultado.tempo_s,
        "programacao_modelo": resultado.programacao,
        "programacao_forca_bruta": prog_bruta,
    }
