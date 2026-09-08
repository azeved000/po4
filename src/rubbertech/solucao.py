"""Extração e avaliação de programações.

O módulo tem duas metades com papéis bem diferentes:

* :func:`avaliar` recebe **apenas a ordem dos itens em cada linha** e recalcula
  do zero tempos, atrasos e objetivo. Não olha para nenhuma variável do solver.
  É o avaliador independente: se o modelo PLI e esta função discordarem, um dos
  dois está errado, e é isso que se quer descobrir.
* :func:`extrair` traduz a solução do solver (as variáveis ``y``) em sequências,
  para então serem reavaliadas por :func:`avaliar`.

Dependências: só :mod:`rubbertech.dominio` em tempo de execução. O tipo
``Variaveis`` de :mod:`rubbertech.modelo` é importado apenas sob
``TYPE_CHECKING``, para anotar :func:`extrair` sem criar um acoplamento real
entre validação e modelo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from rubbertech.dominio import Instancia, Programacao, Tarefa

if TYPE_CHECKING:  # pragma: no cover - apenas para anotação de tipos
    from rubbertech.modelo import Variaveis

#: Tolerância numérica padrão para comparações de ponto flutuante.
TOLERANCIA = 1e-6


def alfa_de(penalidade: float | Mapping[str, float], item: str) -> float:
    """Resolve ``α_i`` a partir de um escalar ou de um mapa por item.

    Aceitar as duas formas evita ter que montar um dicionário completo só para
    dizer "penalize toda antecipação com o mesmo peso".
    """
    if isinstance(penalidade, Mapping):
        return float(penalidade.get(item, 0.0))
    return float(penalidade)


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

    Sobre o que esta função **não** verifica: itens repetidos ou ausentes passam
    sem reclamação. Isso é deliberado — quem detecta esse tipo de defeito é
    :func:`rubbertech.validacao.verificar`, e ele precisa receber a programação
    já construída para poder acusá-lo. O que interrompe a avaliação é apenas o
    que a torna impossível: linha inexistente, item inexistente ou item alocado
    a linha inelegível (este último via :meth:`Instancia.p`).
    """
    tarefas: list[Tarefa] = []
    objetivo = 0.0
    sequencias_normalizadas: dict[str, list[str]] = {}

    for linha in inst.linhas:
        sequencias_normalizadas[linha] = list(sequencias.get(linha, []))

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
            antecipacao = max(0.0, item.d - fim)
            objetivo += item.w * atraso
            objetivo += alfa_de(penalidade_antecipacao, item_id) * antecipacao
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

    return Programacao(
        sequencias=sequencias_normalizadas, tarefas=tarefas, objetivo=objetivo
    )


def extrair(
    inst: Instancia,
    variaveis: "Variaveis",
    penalidade_antecipacao: float | Mapping[str, float] = 0.0,
    limiar: float = 0.5,
) -> Programacao:
    """Reconstrói as sequências a partir das variáveis ``y`` da solução.

    Cada linha é percorrida do nó fictício em diante, seguindo o sucessor
    imediato ativo. Ao final, se sobrar algum arco ativo que não foi visitado, a
    função **levanta erro**: um arco ativo fora das cadeias que partem do nó
    fictício é exatamente a assinatura de um subciclo. Ignorá-lo produziria uma
    programação silenciosamente incompleta — e é justamente esse defeito que os
    experimentos com e sem MTZ precisam conseguir enxergar.

    O objetivo da programação devolvida é **recalculado** por :func:`avaliar`, e
    não lido da função objetivo do solver. Comparar os dois valores é uma
    conferência de graça, feita em :mod:`rubbertech.solver`.
    """
    ativos = {
        chave
        for chave, var in variaveis.y.items()
        if var.value() is not None and var.value() > limiar
    }
    sequencias: dict[str, list[str]] = {}
    visitados: set[tuple[str, str, str]] = set()

    for k in inst.linhas:
        sequencia: list[str] = []
        atual = inst.no_inicial
        while True:
            sucessores = [
                (i, j, linha)
                for (i, j, linha) in ativos
                if linha == k and i == atual and (i, j, linha) not in visitados
            ]
            if not sucessores:
                break
            if len(sucessores) > 1:
                raise ValueError(
                    f"O item '{atual}' tem {len(sucessores)} sucessores ativos na "
                    f"linha '{k}': {[j for _, j, _ in sucessores]}. A solução do "
                    "solver viola a restrição (2')."
                )
            arco = sucessores[0]
            visitados.add(arco)
            atual = arco[1]
            if atual in sequencia:
                raise ValueError(
                    f"Ciclo detectado na linha '{k}' ao reencontrar '{atual}'."
                )
            sequencia.append(atual)
        sequencias[k] = sequencia

    orfaos = sorted(ativos - visitados)
    if orfaos:
        raise ValueError(
            "Há arcos ativos fora das cadeias que partem do nó fictício "
            f"{orfaos} — sintoma de subciclo na solução do solver."
        )

    return avaliar(inst, sequencias, penalidade_antecipacao)


def metricas(prog: Programacao, inst: Instancia | None = None) -> dict[str, object]:
    """Indicadores agregados de uma programação, para o relatório.

    Chaves devolvidas:

    ``atraso_ponderado``
        ``Σ w_i T_i``. Exige ``inst`` (os pesos não estão na programação);
        sem ela, usa ``prog.objetivo``, o que só coincide quando ``α = 0``.
    ``atraso_total``
        ``Σ T_i``, sem pesos — útil para mostrar que o ótimo ponderado
        concentra atraso em poucos itens baratos.
    ``n_atrasados``
        quantos itens terminam depois do prazo.
    ``makespan``
        maior conclusão entre todas as linhas.
    ``tempo_total_setup``
        soma dos setups aplicados; quantifica o custo da troca de família.
    ``ocupacao_por_linha``
        fração do makespan em que cada linha esteve ocupada (processando ou em
        setup). Expõe o desbalanceamento causado pela elegibilidade restrita.
    """
    atraso_total = sum(t.atraso for t in prog.tarefas)
    n_atrasados = sum(1 for t in prog.tarefas if t.atraso > TOLERANCIA)
    makespan = max((t.fim for t in prog.tarefas), default=0.0)
    tempo_total_setup = sum(t.setup for t in prog.tarefas)

    if inst is not None:
        atraso_ponderado = sum(
            inst.itens[t.item].w * t.atraso for t in prog.tarefas
        )
    else:
        atraso_ponderado = prog.objetivo

    ocupacao: dict[str, float] = {}
    for linha, tarefas in _por_linha(prog).items():
        ocupado = sum((t.fim - t.inicio) + t.setup for t in tarefas)
        ocupacao[linha] = ocupado / makespan if makespan > 0 else 0.0

    return {
        "atraso_ponderado": atraso_ponderado,
        "atraso_total": atraso_total,
        "n_atrasados": n_atrasados,
        "makespan": makespan,
        "tempo_total_setup": tempo_total_setup,
        "ocupacao_por_linha": ocupacao,
    }


def _por_linha(prog: Programacao) -> dict[str, list[Tarefa]]:
    """Agrupa as tarefas por linha, mantendo todas as linhas declaradas."""
    grupos: dict[str, list[Tarefa]] = {linha: [] for linha in prog.sequencias}
    for tarefa in prog.tarefas:
        grupos.setdefault(tarefa.linha, []).append(tarefa)
    return grupos
