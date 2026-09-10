"""Construção e resolução do modelo de Programação Linear Inteira Mista.

O modelo é a tradução literal da formulação do relatório
(``R_m | s_ij, M_i | Σ w_i T_i``). Cada bloco de restrições cita, no comentário
e no nome PuLP, o número correspondente da formulação — é o que permite conferir
código contra texto sem depender de memória.

Este módulo importa apenas :mod:`dados` (e o PuLP). Em particular **não** importa
:mod:`conferencia`: :func:`resolver` devolve as sequências que o solver
encontrou, e quem recalcula o objetivo é o avaliador independente, do lado de
fora. Assim o número que confere a solução nunca passa pelo solver.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import pulp

from rubbertech.dados import Instancia


# ======================================================================
# Construção
# ======================================================================
@dataclass
class ConfigModelo:
    """Opções de construção do modelo.

    Atributos:
        usar_mtz: liga as restrições (6) de Miller-Tucker-Zemlin. Elas são
            **redundantes** — as restrições (4') já impedem subciclos, pois um
            ciclo implicaria ``C[i] > C[i]`` — e entram apenas para fortalecer a
            relaxação linear. É configurável porque medir esse efeito é um dos
            experimentos do trabalho (``main.py experimentos --experimento mtz``).
        penalidade_antecipacao: ``α``, escalar ou por item. Com ``α = 0`` (o
            padrão) o objetivo é o atraso ponderado puro; com ``α > 0`` a
            estocagem limitada é penalizada e a produção tende ao just-in-time.
        big_m: valor de ``V``. ``None`` calcula a partir da instância, que é o
            recomendado — ver :meth:`Instancia.big_m`.
    """

    usar_mtz: bool = True
    penalidade_antecipacao: float | dict[str, float] = 0.0
    big_m: float | None = None

    def alfa(self, item: str) -> float:
        """``α_i`` a partir de um escalar ou de um mapa por item."""
        if isinstance(self.penalidade_antecipacao, dict):
            return float(self.penalidade_antecipacao.get(item, 0.0))
        return float(self.penalidade_antecipacao)


@dataclass
class Variaveis:
    """Os dicionários de variáveis de decisão, por chave da formulação."""

    x: dict[tuple[str, str], pulp.LpVariable] = field(default_factory=dict)
    y: dict[tuple[str, str, str], pulp.LpVariable] = field(default_factory=dict)
    C: dict[str, pulp.LpVariable] = field(default_factory=dict)
    T: dict[str, pulp.LpVariable] = field(default_factory=dict)
    A: dict[str, pulp.LpVariable] = field(default_factory=dict)
    u: dict[str, pulp.LpVariable] = field(default_factory=dict)
    #: Valor de ``V`` efetivamente usado, para constar do relatório.
    big_m: float = 0.0


def construir(
    inst: Instancia, cfg: ConfigModelo | None = None
) -> tuple[pulp.LpProblem, Variaveis]:
    """Monta o MILP da instância e devolve ``(problema, variáveis)``.

    Decisões de modelagem que precisam estar claras:

    * **Elegibilidade por domínio.** ``x[i,k]`` e ``y[i,j,k]`` só são criados
      para linhas elegíveis. Isso é mais forte do que criar a variável e fixá-la
      em zero: a variável simplesmente não existe, o pré-processamento do solver
      não precisa descobrir nada e o modelo encolhe de verdade.
    * **Linearização de T.** As restrições (5) dão apenas ``T_i ≥ C_i - d_i`` e
      ``T_i ≥ 0``; o valor exato ``T_i = max(0, C_i - d_i)`` só vale no ótimo
      porque ``w_i > 0`` e o objetivo minimiza. Com ``w_i = 0`` a variável
      ficaria livre acima do limite (o valor ótimo continua correto, mas ``T_i``
      deixa de ser legível) — por isso a solução é sempre reavaliada por
      :func:`conferencia.avaliar`.
    * **Restrições nomeadas.** Sem nome, o ``.lp`` exportado vira ``_C1``,
      ``_C2``… e depurar um modelo com milhares de restrições vira adivinhação.
      Os nomes seguem a numeração da formulação do relatório.
    """
    cfg = cfg or ConfigModelo()
    inst.validar()

    big_m = cfg.big_m if cfg.big_m is not None else inst.big_m()
    n = inst.n
    prob = pulp.LpProblem("RubberTech_atraso_ponderado", pulp.LpMinimize)
    var = Variaveis(big_m=big_m)

    # ---- variáveis ----------------------------------------------------
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
        # propósito — a integralidade é implicada por (6) e deixá-la contínua
        # não acrescenta nós à árvore de busca.
        for i in inst.J:
            var.u[i] = pulp.LpVariable(f"u_{i}", lowBound=1, upBound=max(n, 1))

    # ---- objetivo: min Σ_i ( w_i·T_i + α_i·A_i ) ----------------------
    prob += (
        pulp.lpSum(
            inst.itens[i].w * var.T[i] + cfg.alfa(i) * var.A[i] for i in inst.J
        ),
        "atraso_ponderado_total",
    )

    # ---- (1) cada item é produzido em exatamente uma linha elegível ---
    for i in inst.J:
        prob += (
            pulp.lpSum(var.x[(i, k)] for k in inst.elegiveis(i)) == 1,
            f"alocacao_{i}",
        )

    # ---- (2) todo item alocado a k tem exatamente um predecessor -------
    #      imediato em k (que pode ser o nó fictício).
    for j in inst.J:
        for k in inst.elegiveis(j):
            prob += (
                pulp.lpSum(var.y[(i, j, k)] for i in inst.J0 if (i, j, k) in var.y)
                == var.x[(j, k)],
                f"entrada_{j}_{k}",
            )

    # ---- (2') todo item tem no máximo um sucessor imediato na linha ----
    #       em que roda (o último da linha não tem nenhum).
    for i in inst.J:
        for k in inst.elegiveis(i):
            prob += (
                pulp.lpSum(var.y[(i, j, k)] for j in inst.J if (i, j, k) in var.y)
                <= var.x[(i, k)],
                f"saida_{i}_{k}",
            )

    # ---- (3) cada linha começa no máximo uma cadeia --------------------
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

    # ---- (4) e (4') datação por big-M, ativas só quando o arco é usado -
    for (i, j, k), variavel in var.y.items():
        if i == inst.no_inicial:
            # (4) primeiro item da linha: parte de zero, paga o setup inicial.
            prob += (
                var.C[j] >= inst.s(i, j) + inst.p(j, k) - big_m * (1 - variavel),
                f"tempo_inicial_{j}_{k}",
            )
        else:
            # (4') item j logo após i: herda C_i e paga o setup do par real.
            prob += (
                var.C[j]
                >= var.C[i] + inst.s(i, j) + inst.p(j, k) - big_m * (1 - variavel),
                f"tempo_{i}_{j}_{k}",
            )

    # ---- (5) e (5') atraso e antecipação ------------------------------
    for i in inst.J:
        item = inst.itens[i]
        prob += (var.T[i] >= var.C[i] - item.d, f"atraso_{i}")
        prob += (var.A[i] >= item.d - var.C[i], f"antecipacao_{i}")

    # ---- (6) MTZ — opcional e redundante ------------------------------
    if cfg.usar_mtz:
        for (i, j, k), variavel in var.y.items():
            if i == inst.no_inicial:
                continue
            prob += (var.u[i] - var.u[j] + n * variavel <= n - 1, f"mtz_{i}_{j}_{k}")

    return prob, var


def tamanho(prob: pulp.LpProblem) -> tuple[int, int]:
    """``(nº de variáveis, nº de restrições)`` do modelo construído."""
    return len(prob.variables()), len(prob.constraints)


def extrair_sequencias(
    inst: Instancia, variaveis: Variaveis, limiar: float = 0.5
) -> dict[str, list[str]]:
    """Reconstrói ``linha -> ordem dos itens`` a partir das variáveis ``y``.

    Cada linha é percorrida do nó fictício em diante, seguindo o sucessor
    imediato ativo. Ao final, se sobrar arco ativo não visitado, a função
    **levanta erro**: um arco ativo fora das cadeias que partem do nó fictício é
    exatamente a assinatura de um subciclo. Ignorá-lo produziria uma programação
    silenciosamente incompleta — e é justamente esse defeito que os experimentos
    com e sem MTZ precisam conseguir enxergar.

    Devolve só a ordem, de propósito: datas, atrasos e objetivo são recalculados
    fora daqui, por :func:`conferencia.avaliar`, sem olhar variável de solver.
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
                arco
                for arco in ativos
                if arco[2] == k and arco[0] == atual and arco not in visitados
            ]
            if not sucessores:
                break
            if len(sucessores) > 1:
                raise ValueError(
                    f"O item '{atual}' tem {len(sucessores)} sucessores ativos na "
                    f"linha '{k}': {[j for _, j, _ in sucessores]}. A solução do "
                    "solver viola a restrição (2')."
                )
            visitados.add(sucessores[0])
            atual = sucessores[0][1]
            if atual in sequencia:
                raise ValueError(
                    f"Ciclo detectado na linha '{k}' ao reencontrar '{atual}'."
                )
            sequencia.append(atual)
        sequencias[k] = sequencia

    if orfaos := sorted(ativos - visitados):
        raise ValueError(
            "Há arcos ativos fora das cadeias que partem do nó fictício "
            f"{orfaos} — sintoma de subciclo na solução do solver."
        )
    return sequencias


# ======================================================================
# Resolução
# ======================================================================
#: Status normalizados para o relatório.
STATUS_OTIMO = "Optimal"
STATUS_VIAVEL = "Not Solved"  # limite de tempo com solução incumbente
STATUS_INVIAVEL = "Infeasible"
STATUS_INDEFINIDO = "Undefined"

#: Limite de tempo padrão, em segundos. Todos os experimentos do relatório usam
#: **o mesmo** valor: comparar tabelas resolvidas com limites diferentes produz
#: objetivos incomparáveis para o mesmo n. Vale para os três subcomandos
#: (``resolver``, ``validar``, ``experimentos``); ``--tempo-limite`` sobrepõe por
#: execução. Ver "Como alterar o limite de tempo do solver" no README.
TEMPO_LIMITE_PADRAO = 300


@dataclass
class Resultado:
    """Tudo o que a resolução produziu, incluindo o que ela *não* provou.

    Atributos:
        status: ``Optimal`` (ótimo provado), ``Not Solved`` (parou no limite de
            tempo com incumbente), ``Infeasible`` ou ``Undefined``.
        objetivo: valor da função objetivo da melhor solução encontrada. É
            ``None`` quando não há solução — nunca se devolve um número sem o
            status que diz o que ele significa.
        limite_inferior: melhor limitante inferior conhecido (``= objetivo``
            quando o ótimo foi provado).
        gap: distância relativa entre incumbente e limite inferior, **em
            fração**. Use :attr:`gap_percentual` para exibir ou gravar.
        sequencias: ``linha -> ordem dos itens``. É tudo o que sai do solver; o
            objetivo correspondente é recalculado por :mod:`conferencia`.
        tempo_limite: o limite de tempo (segundos) com que o solver foi chamado
            — não o tempo que ele de fato gastou (``tempo_s``). É o que permite
            ao relatório dizer *qual* limite foi atingido quando ``status ==
            "Not Solved"``, em vez de só que algum limite foi atingido.
    """

    status: str
    objetivo: float | None
    limite_inferior: float | None
    gap: float | None
    tempo_s: float
    n_variaveis: int
    n_restricoes: int
    sequencias: dict[str, list[str]] | None
    #: Mensagem crua do solver ("Stopped on time limit" etc.), para depuração.
    mensagem: str = ""
    tempo_limite: int | None = None

    @property
    def otimo_provado(self) -> bool:
        """Só isto autoriza chamar o valor de "ótimo" no relatório."""
        return self.status == STATUS_OTIMO

    @property
    def gap_percentual(self) -> float | None:
        """O gap em **porcentagem** — a unidade usada na tela e nos CSVs."""
        return None if self.gap is None else 100.0 * self.gap


def criar_solver(
    nome: str = "CBC",
    tempo_limite: int | None = TEMPO_LIMITE_PADRAO,
    msg: bool = False,
    **extras,
) -> pulp.LpSolver:
    """Devolve o solver pedido, com CBC como padrão e HiGHS plugável.

    O CBC vem junto com o PuLP e não exige instalação adicional, o que mantém o
    trabalho reprodutível em qualquer máquina do laboratório. O HiGHS é aceito
    para quem o tiver instalado (``pip install highspy``).
    """
    normalizado = nome.strip().upper()
    if normalizado in {"CBC", "PULP_CBC_CMD"}:
        return pulp.PULP_CBC_CMD(msg=msg, timeLimit=tempo_limite, **extras)
    if normalizado in {"HIGHS", "HIGHS_CMD"}:
        classe = getattr(pulp, "HiGHS_CMD", None)
        if classe is None or not classe().available():
            raise RuntimeError(
                "HiGHS não está disponível neste ambiente. Instale 'highspy' ou "
                "use solver_nome='CBC'."
            )
        return classe(msg=msg, timeLimit=tempo_limite, **extras)
    raise ValueError(f"Solver desconhecido: '{nome}'. Use 'CBC' ou 'HiGHS'.")


def _ler_log_cbc(caminho: Path) -> tuple[float | None, float | None, str]:
    """Extrai ``(limite_inferior, gap, mensagem)`` do log textual do CBC.

    O ``PULP_CBC_CMD`` não expõe limite inferior nem gap programaticamente, e o
    CBC só os imprime quando **não** prova otimalidade; quando prova, o limite é
    o próprio objetivo e o gap é zero, e isso é tratado por quem chama.
    """
    if not caminho.exists():
        return None, None, ""
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    limite = gap = None
    if achado := re.search(r"^Lower bound:\s*(-?[\d.eE+]+)", texto, re.M):
        limite = float(achado.group(1))
    if achado := re.search(r"^Gap:\s*(-?[\d.eE+]+)", texto, re.M):
        gap = float(achado.group(1))
    mensagem = ""
    if achado := re.search(r"^Result - (.+)$", texto, re.M):
        mensagem = achado.group(1).strip()
    return limite, gap, mensagem


def resolver(
    inst: Instancia,
    cfg: ConfigModelo | None = None,
    tempo_limite: int | None = TEMPO_LIMITE_PADRAO,
    solver_nome: str = "CBC",
    msg: bool = False,
) -> Resultado:
    """Constrói o modelo, resolve e devolve o :class:`Resultado` completo.

    O status é sempre coerente com o objetivo devolvido:

    * ``Optimal`` — ótimo provado; ``gap = 0``.
    * ``Not Solved`` — o solver parou no limite de tempo com uma solução viável
      na mão. O objetivo é um **limitante superior**, não o ótimo.
    * ``Infeasible`` / ``Undefined`` — não há programação a devolver.
    """
    cfg = cfg or ConfigModelo()
    inicio = time.perf_counter()

    prob, variaveis = construir(inst, cfg)
    n_variaveis, n_restricoes = tamanho(prob)

    with tempfile.TemporaryDirectory(prefix="rubbertech_") as pasta:
        caminho_log = Path(pasta) / "cbc.log"
        solver = criar_solver(
            solver_nome, tempo_limite=tempo_limite, msg=msg, logPath=str(caminho_log)
        )
        prob.solve(solver)
        limite_log, gap_log, mensagem = _ler_log_cbc(caminho_log)

    tempo_s = time.perf_counter() - inicio
    status_bruto = pulp.LpStatus[prob.status]
    tem_solucao = prob.status == pulp.LpStatusOptimal and any(
        var.value() is not None for var in variaveis.x.values()
    )

    # O CBC devolve status "Optimal" também quando para no limite de tempo com
    # uma incumbente; o log é a única fonte que distingue os dois casos.
    parou_no_tempo = "time limit" in mensagem.lower() or (
        gap_log is not None and gap_log > 1e-9
    )
    if status_bruto == "Optimal" and tem_solucao:
        status = STATUS_VIAVEL if parou_no_tempo else STATUS_OTIMO
    elif status_bruto == "Infeasible":
        status = STATUS_INVIAVEL
    elif status_bruto == "Not Solved":
        status = STATUS_VIAVEL if tem_solucao else STATUS_INDEFINIDO
    else:
        status = STATUS_INDEFINIDO

    if status in {STATUS_INVIAVEL, STATUS_INDEFINIDO}:
        return Resultado(
            status=status,
            objetivo=None,
            limite_inferior=limite_log,
            gap=None,
            tempo_s=tempo_s,
            n_variaveis=n_variaveis,
            n_restricoes=n_restricoes,
            sequencias=None,
            mensagem=mensagem or status_bruto,
            tempo_limite=tempo_limite,
        )

    objetivo = pulp.value(prob.objective)
    if status == STATUS_OTIMO:
        limite_inferior: float | None = objetivo
        gap: float | None = 0.0
    else:
        limite_inferior = limite_log
        if gap_log is not None:
            gap = gap_log
        elif limite_inferior not in (None, 0) and objetivo is not None:
            # Mesma convenção do CBC: gap relativo ao **limite inferior**, e não
            # ao incumbente. Por isso valores acima de 100% são normais quando o
            # limite ainda está fraco.
            gap = abs(objetivo - limite_inferior) / abs(limite_inferior)
        else:
            gap = None

    return Resultado(
        status=status,
        objetivo=objetivo,
        limite_inferior=limite_inferior,
        gap=gap,
        tempo_s=tempo_s,
        n_variaveis=n_variaveis,
        n_restricoes=n_restricoes,
        sequencias=extrair_sequencias(inst, variaveis),
        mensagem=mensagem or status_bruto,
        tempo_limite=tempo_limite,
    )
