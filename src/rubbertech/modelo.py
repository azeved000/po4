"""Construção do modelo de Programação Linear Inteira Mista.

O modelo é a tradução literal da formulação do relatório
(``R_m | s_ij, M_i | Σ w_i T_i``). Cada bloco de restrições cita, no comentário
e no nome PuLP, o número correspondente da formulação — é o que permite
conferir código contra texto sem depender de memória.

Este módulo importa apenas :mod:`rubbertech.dominio`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from rubbertech.dominio import Instancia


@dataclass
class ConfigModelo:
    """Opções de construção do modelo.

    Atributos:
        usar_mtz: liga as restrições (6) de Miller-Tucker-Zemlin. Elas são
            **redundantes** — as restrições (4') já impedem subciclos, pois um
            ciclo implicaria ``C[i] > C[i]`` — e entram apenas para fortalecer a
            relaxação linear. É configurável porque medir esse efeito é um dos
            experimentos do trabalho (ver ``scripts/experimentos.py``).
        penalidade_antecipacao: ``α``, escalar ou por item. Com ``α = 0`` (o
            padrão) o objetivo é o atraso ponderado puro; com ``α > 0`` a
            estocagem limitada é penalizada e a produção tende ao just-in-time.
        big_m: valor de ``V``. ``None`` calcula a partir da instância, que é o
            recomendado — ver :meth:`Instancia.big_m`.
    """

    usar_mtz: bool = True
    penalidade_antecipacao: float | dict[str, float] = 0.0
    big_m: float | None = None


@dataclass
class Variaveis:
    """Os dicionários de variáveis de decisão do modelo construído.

    Guardados por chave da formulação para que :func:`rubbertech.solucao.extrair`
    e os testes possam consultá-los sem depender de nomes gerados pelo PuLP.
    """

    x: dict[tuple[str, str], pulp.LpVariable] = field(default_factory=dict)
    y: dict[tuple[str, str, str], pulp.LpVariable] = field(default_factory=dict)
    C: dict[str, pulp.LpVariable] = field(default_factory=dict)
    T: dict[str, pulp.LpVariable] = field(default_factory=dict)
    A: dict[str, pulp.LpVariable] = field(default_factory=dict)
    u: dict[str, pulp.LpVariable] = field(default_factory=dict)
    #: Valor de ``V`` efetivamente usado, para constar do relatório.
    big_m: float = 0.0


def _alfa(cfg: ConfigModelo, item: str) -> float:
    """``α_i`` a partir de um escalar ou de um mapa por item."""
    if isinstance(cfg.penalidade_antecipacao, dict):
        return float(cfg.penalidade_antecipacao.get(item, 0.0))
    return float(cfg.penalidade_antecipacao)


def construir(
    inst: Instancia, cfg: ConfigModelo | None = None
) -> tuple[pulp.LpProblem, Variaveis]:
    """Monta o MILP da instância e devolve ``(problema, variáveis)``.

    Decisões de modelagem que estão no código e precisam estar claras:

    * **Elegibilidade por domínio.** ``x[i,k]`` e ``y[i,j,k]`` só são criados
      para linhas elegíveis. Isso é mais forte do que criar a variável e fixá-la
      em zero: a variável simplesmente não existe, o pré-processamento do solver
      não precisa descobrir nada e o modelo encolhe de verdade.
    * **Linearização de T.** As restrições (5) dão apenas ``T_i ≥ C_i - d_i`` e
      ``T_i ≥ 0``; o valor exato ``T_i = max(0, C_i - d_i)`` só vale no ótimo
      porque ``w_i > 0`` e o objetivo minimiza — qualquer folga em ``T_i``
      custaria dinheiro. Com ``w_i = 0`` a variável ficaria livre acima do
      limite (o valor ótimo continua correto, mas ``T_i`` deixa de ser legível);
      por isso o relatório sempre reavalia a solução com
      :func:`rubbertech.solucao.avaliar`.
    * **Restrições nomeadas.** Sem nome, o ``.lp`` exportado vira ``_C1``,
      ``_C2``… e depurar um modelo com milhares de restrições vira adivinhação.
    """
    cfg = cfg or ConfigModelo()
    inst.validar()

    big_m = cfg.big_m if cfg.big_m is not None else inst.big_m()
    n = inst.n
    prob = pulp.LpProblem("RubberTech_atraso_ponderado", pulp.LpMinimize)
    var = Variaveis(big_m=big_m)

    # ------------------------------------------------------------------
    # Variáveis
    # ------------------------------------------------------------------
    for i in inst.J:
        for k in inst.elegiveis(i):
            var.x[(i, k)] = pulp.LpVariable(f"x_{i}_{k}", cat=pulp.LpBinary)

    for i, j, k in inst.arcos():
        var.y[(i, j, k)] = pulp.LpVariable(f"y_{i}_{j}_{k}", cat=pulp.LpBinary)

    for i in inst.J:
        var.C[i] = pulp.LpVariable(f"C_{i}", lowBound=0)
        var.T[i] = pulp.LpVariable(f"T_{i}", lowBound=0)
        var.A[i] = pulp.LpVariable(f"A_{i}", lowBound=0)

    if cfg.usar_mtz:
        # u ∈ [1, n]: posição do item na sequência da sua linha. Contínua de
        # propósito — a integralidade é implicada pelas restrições (6) e deixá-la
        # contínua não acrescenta nós à árvore de busca.
        for i in inst.J:
            var.u[i] = pulp.LpVariable(f"u_{i}", lowBound=1, upBound=max(n, 1))

    # ------------------------------------------------------------------
    # Objetivo: min Σ_i ( w_i·T_i + α_i·A_i )
    # ------------------------------------------------------------------
    prob += (
        pulp.lpSum(
            inst.itens[i].w * var.T[i] + _alfa(cfg, i) * var.A[i] for i in inst.J
        ),
        "atraso_ponderado_total",
    )

    # ------------------------------------------------------------------
    # (1) Cada item é produzido em exatamente uma linha elegível.
    # ------------------------------------------------------------------
    for i in inst.J:
        prob += (
            pulp.lpSum(var.x[(i, k)] for k in inst.elegiveis(i)) == 1,
            f"alocacao_{i}",
        )

    # ------------------------------------------------------------------
    # (2) Todo item alocado a k tem exatamente um predecessor imediato em k
    #     (que pode ser o nó fictício).
    # ------------------------------------------------------------------
    for j in inst.J:
        for k in inst.elegiveis(j):
            prob += (
                pulp.lpSum(
                    var.y[(i, j, k)] for i in inst.J0 if (i, j, k) in var.y
                )
                == var.x[(j, k)],
                f"entrada_{j}_{k}",
            )

    # ------------------------------------------------------------------
    # (2') Todo item tem no máximo um sucessor imediato na linha em que roda
    #      (o último da linha não tem nenhum).
    # ------------------------------------------------------------------
    for i in inst.J:
        for k in inst.elegiveis(i):
            prob += (
                pulp.lpSum(
                    var.y[(i, j, k)] for j in inst.J if (i, j, k) in var.y
                )
                <= var.x[(i, k)],
                f"saida_{i}_{k}",
            )

    # ------------------------------------------------------------------
    # (3) Cada linha começa no máximo uma cadeia.
    # ------------------------------------------------------------------
    for k in inst.M:
        prob += (
            pulp.lpSum(
                var.y[(inst.no_inicial, j, k)]
                for j in inst.J
                if (inst.no_inicial, j, k) in var.y
            )
            <= 1,
            f"origem_{k}",
        )

    # ------------------------------------------------------------------
    # (4) e (4') Datação por big-M. Ativas apenas quando o arco é usado.
    # ------------------------------------------------------------------
    for (i, j, k), variavel in var.y.items():
        if i == inst.no_inicial:
            # (4) primeiro item da linha: parte de zero, paga o setup inicial.
            prob += (
                var.C[j]
                >= inst.s(i, j) + inst.p(j, k) - big_m * (1 - variavel),
                f"tempo_inicial_{j}_{k}",
            )
        else:
            # (4') item j logo após i: herda C_i e paga o setup do par real.
            prob += (
                var.C[j]
                >= var.C[i] + inst.s(i, j) + inst.p(j, k) - big_m * (1 - variavel),
                f"tempo_{i}_{j}_{k}",
            )

    # ------------------------------------------------------------------
    # (5) e (5') Atraso e antecipação.
    # ------------------------------------------------------------------
    for i in inst.J:
        item = inst.itens[i]
        prob += (var.T[i] >= var.C[i] - item.d, f"atraso_{i}")
        prob += (var.A[i] >= item.d - var.C[i], f"antecipacao_{i}")

    # ------------------------------------------------------------------
    # (6) MTZ — opcional e redundante; ver ConfigModelo.usar_mtz.
    # ------------------------------------------------------------------
    if cfg.usar_mtz:
        for (i, j, k), variavel in var.y.items():
            if i == inst.no_inicial:
                continue
            prob += (
                var.u[i] - var.u[j] + n * variavel <= n - 1,
                f"mtz_{i}_{j}_{k}",
            )

    return prob, var


def tamanho(prob: pulp.LpProblem) -> tuple[int, int]:
    """``(nº de variáveis, nº de restrições)`` do modelo construído."""
    return len(prob.variables()), len(prob.constraints)
