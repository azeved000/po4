"""Conferência independente: avaliador, verificador, força bruta e EDD.

Nada aqui usa o solver para julgar o solver. Este módulo importa **apenas**
:mod:`dados` — nem :mod:`modelo`, nem PuLP. Essa restrição não é estética: um
modelo com erro de sinal, big-M curto ou setup trocado continua devolvendo
"Optimal" com toda a confiança do mundo, e a única evidência de que a
formulação está certa é recalcular tudo por um caminho que não passa pelo
solver.

As três peças, em ordem de força:

* :func:`avaliar` — recebe **só a ordem dos itens em cada linha** e recalcula do
  zero setups, tempos, atrasos e objetivo;
* :func:`verificar` — confronta uma programação já montada com a instância e
  lista tudo o que estiver errado;
* :func:`forca_bruta` — enumeração exaustiva, dá o ótimo verdadeiro sem solver.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from rubbertech.dados import Instancia, Programacao, Tarefa

#: Tolerância numérica padrão para comparações de ponto flutuante.
TOLERANCIA = 1e-6
#: Limite acima do qual a enumeração exaustiva é recusada (ver `forca_bruta`).
MAX_ITENS_FORCA_BRUTA = 8


def alfa_de(penalidade: float | Mapping[str, float], item: str) -> float:
    """``α_i`` a partir de um escalar ou de um mapa por item."""
    if isinstance(penalidade, Mapping):
        return float(penalidade.get(item, 0.0))
    return float(penalidade)


# ======================================================================
# Avaliador independente
# ======================================================================
def avaliar(
    inst: Instancia,
    sequencias: Mapping[str, Sequence[str]],
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
) -> Programacao:
    """Recalcula uma programação a partir apenas da ordem dos itens por linha.

    Cada linha é percorrida do nó fictício em diante, aplicando o setup do par
    consecutivo real e, em seguida, o tempo de processamento::

        C_j = C_i + s[i,j] + p[j,k]      (o primeiro item usa s[0,j] e C_i = 0)
        T_j = max(0, C_j - d_j)
        A_j = max(0, d_j - C_j)

    O objetivo devolvido é ``Σ_i (w_i T_i + α_i A_i)``.

    O que esta função **não** verifica: itens repetidos ou ausentes passam sem
    reclamação. É deliberado — quem detecta esse tipo de defeito é
    :func:`verificar`, e ele precisa receber a programação já construída para
    poder acusá-lo. Interrompe a avaliação apenas o que a torna impossível:
    linha inexistente, item inexistente ou item em linha inelegível.
    """
    tarefas: list[Tarefa] = []
    objetivo = 0.0
    normalizadas = {linha: list(sequencias.get(linha, [])) for linha in inst.linhas}

    for linha, sequencia in sequencias.items():
        if linha not in inst.linhas:
            raise KeyError(
                f"Linha '{linha}' não existe na instância (linhas: {inst.linhas})."
            )
        anterior = inst.no_inicial
        relogio = 0.0
        for item_id in sequencia:
            if item_id not in inst.itens:
                raise KeyError(f"Item '{item_id}' não existe na instância.")
            item = inst.itens[item_id]
            setup = inst.s(anterior, item_id)
            inicio = relogio + setup
            fim = inicio + inst.p(item_id, linha)
            atraso = max(0.0, fim - item.d)
            objetivo += item.w * atraso
            objetivo += alfa_de(penalidade_antecipacao, item_id) * max(
                0.0, item.d - fim
            )
            tarefas.append(
                Tarefa(
                    item=item_id,
                    linha=linha,
                    inicio=inicio,
                    fim=fim,
                    setup=setup,
                    atraso=atraso,
                )
            )
            relogio = fim
            anterior = item_id

    return Programacao(sequencias=normalizadas, tarefas=tarefas, objetivo=objetivo)


# ======================================================================
# Verificador
# ======================================================================
def verificar(
    inst: Instancia,
    prog: Programacao,
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
    tolerancia: float = TOLERANCIA,
) -> list[str]:
    """Devolve a lista de violações de uma programação (vazia = programação sã).

    Retornar uma lista em vez de levantar exceção é proposital: quando algo dá
    errado, interessa ver *todos* os defeitos de uma vez, e não o primeiro.

    Verifica cobertura (cada item exatamente uma vez), elegibilidade de linha,
    ausência de sobreposição temporal, coerência entre os setups aplicados e os
    pares consecutivos reais, duração das tarefas, cálculo do atraso e, por fim,
    se o objetivo declarado bate com o recalculado por :func:`avaliar`.
    """
    violacoes: list[str] = []

    # ---- cobertura: todo item exatamente uma vez ----------------------
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

    # ---- linhas, elegibilidade e coerência com as tarefas -------------
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
        cronologica = [t.item for t in prog.tarefas_da_linha(linha)]
        if cronologica != list(sequencia):
            violacoes.append(
                f"Na linha '{linha}', a ordem cronológica das tarefas "
                f"{cronologica} não corresponde à sequência declarada "
                f"{list(sequencia)}."
            )
    for linha in {t.linha for t in prog.tarefas} - set(prog.sequencias):
        violacoes.append(
            f"Há tarefas na linha '{linha}', que não consta das sequências."
        )

    # ---- tempos, setups e atrasos -------------------------------------
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

            if (par := (anterior, item_id)) in inst.setup:
                esperado = inst.setup[par]
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
                duracao = inst.p(item_id, linha)
                if abs((tarefa.fim - tarefa.inicio) - duracao) > tolerancia:
                    violacoes.append(
                        f"Duração incorreta de '{item_id}' na linha '{linha}': "
                        f"{tarefa.fim - tarefa.inicio}, esperado "
                        f"p['{item_id}','{linha}'] = {duracao}."
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


@dataclass
class Conferencia:
    """Resultado de conferir uma solução do solver por fora dele.

    ``divergencia`` é ``objetivo recalculado - objetivo do solver``; deve ser
    ~0. É a conferência mais barata do projeto e a que pega erro de modelagem
    silencioso.
    """

    programacao: Programacao
    violacoes: list[str] = field(default_factory=list)
    divergencia: float | None = None

    @property
    def sem_violacoes(self) -> bool:
        return not self.violacoes


def conferir(
    inst: Instancia,
    sequencias: Mapping[str, Sequence[str]],
    objetivo_solver: float | None = None,
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
) -> Conferencia:
    """Avalia as sequências do zero, verifica-as e mede a divergência.

    É o ponto de entrada que :mod:`main` usa depois de resolver: o solver
    entrega apenas a **ordem** dos itens, e todo o resto do número volta a ser
    calculado aqui, sem PuLP no caminho.
    """
    prog = avaliar(inst, sequencias, penalidade_antecipacao)
    return Conferencia(
        programacao=prog,
        violacoes=verificar(inst, prog, penalidade_antecipacao),
        divergencia=(
            None if objetivo_solver is None else prog.objetivo - objetivo_solver
        ),
    )


# ======================================================================
# Força bruta
# ======================================================================
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

    Levanta ``ValueError`` acima de ``max_itens`` itens — a explosão é fatorial
    e um engano custaria horas de espera silenciosa.
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

        # Ramo 1: encerrar esta linha.
        if indice_linha == len(linhas) - 1:
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
                indice_linha, item_id, fim, restantes - {item_id}, acumulado + custo
            )
            sequencias[linha].pop()

    expandir(0, inst.no_inicial, 0.0, frozenset(ordem), 0.0)

    if melhor_sequencias is None:
        raise ValueError(
            "A enumeração exaustiva não encontrou nenhuma programação viável; "
            "verifique a elegibilidade dos itens."
        )
    return melhor_custo, avaliar(inst, melhor_sequencias, penalidade_antecipacao)


# ======================================================================
# EDD — regra de despacho, APENAS para comparação
# ======================================================================
def edd(
    inst: Instancia, penalidade_antecipacao: float | Mapping[str, float] = 0.0
) -> Programacao:
    """EDD (*earliest due date*): menor prazo primeiro.

    **Não é o método de solução deste trabalho.** A restrição metodológica da
    disciplina é rígida: a solução entregue é obtida por Programação Linear
    Inteira Mista. O EDD existe só para quantificar, no relatório, o ganho do
    modelo exato — é a coluna de comparação, nunca um resultado.

    Cada item vai para a linha elegível em que **terminaria mais cedo**, dado o
    que já foi programado nela (incluindo o setup do par real). A regra é míope
    quanto ao setup dependente da sequência: ordena por prazo e nunca antecipa
    que agrupar itens da mesma família economiza preparação — que é exatamente a
    decisão que o modelo exato toma. O objetivo é recalculado por
    :func:`avaliar`, de modo que a comparação use a mesma conta dos dois lados.
    """
    sequencias: dict[str, list[str]] = {linha: [] for linha in inst.linhas}
    relogio = {linha: 0.0 for linha in inst.linhas}
    ultimo = {linha: inst.no_inicial for linha in inst.linhas}

    for item in sorted(inst.itens.values(), key=lambda it: it.d):
        melhor_linha, melhor_fim = None, math.inf
        for linha in inst.elegiveis(item.id):
            fim = relogio[linha] + inst.s(ultimo[linha], item.id) + inst.p(
                item.id, linha
            )
            if fim < melhor_fim:
                melhor_linha, melhor_fim = linha, fim
        assert melhor_linha is not None  # validar() garante ao menos uma linha
        sequencias[melhor_linha].append(item.id)
        relogio[melhor_linha] = melhor_fim
        ultimo[melhor_linha] = item.id

    return avaliar(inst, sequencias, penalidade_antecipacao)
