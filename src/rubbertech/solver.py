"""Execução do modelo e coleta de estatísticas da resolução.

Além de chamar o solver, este módulo faz duas coisas que o relatório precisa:

1. distingue com clareza "ótimo provado" de "solução viável encontrada dentro do
   limite de tempo". Em instâncias de 80 itens o CBC frequentemente devolve um
   valor excelente sem provar otimalidade, e apresentar esse número como ótimo
   seria falso;
2. extrai limite inferior e gap do log do CBC, porque o ``PULP_CBC_CMD`` não os
   expõe programaticamente.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pulp

from rubbertech.dominio import Instancia, Programacao
from rubbertech.modelo import ConfigModelo, construir, tamanho
from rubbertech.solucao import extrair

#: Status possíveis, normalizados para o relatório.
STATUS_OTIMO = "Optimal"
STATUS_VIAVEL = "Not Solved"  # limite de tempo com solução incumbente
STATUS_INVIAVEL = "Infeasible"
STATUS_INDEFINIDO = "Undefined"


@dataclass
class Resultado:
    """Tudo o que a resolução produziu, incluindo o que ela *não* provou.

    Atributos:
        status: ``Optimal`` (ótimo provado), ``Not Solved`` (parou no limite de
            tempo com solução incumbente), ``Infeasible`` ou ``Undefined``.
        objetivo: valor da função objetivo da melhor solução encontrada. É
            ``None`` quando não há solução — nunca se devolve um número sem o
            status que diz o que ele significa.
        limite_inferior: melhor limitante inferior conhecido (``= objetivo``
            quando o ótimo foi provado).
        gap: distância relativa entre incumbente e limite inferior.
        tempo_s: tempo de parede da resolução, incluindo a construção do modelo.
        n_variaveis, n_restricoes: tamanho do modelo, para as tabelas de escala.
        programacao: solução já reavaliada de forma independente por
            :func:`rubbertech.solucao.avaliar`.
    """

    status: str
    objetivo: float | None
    limite_inferior: float | None
    gap: float | None
    tempo_s: float
    n_variaveis: int
    n_restricoes: int
    programacao: Programacao | None
    #: Diferença entre o objetivo do solver e o recalculado; deve ser ~0.
    divergencia_recalculo: float | None = None
    #: Mensagem crua do solver ("Stopped on time limit" etc.), para depuração.
    mensagem: str = ""

    @property
    def otimo_provado(self) -> bool:
        """Só isto autoriza chamar o valor de "ótimo" no relatório."""
        return self.status == STATUS_OTIMO


def criar_solver(
    nome: str = "CBC", tempo_limite: int | None = 300, msg: bool = False, **extras
) -> pulp.LpSolver:
    """Devolve o solver pedido, com CBC como padrão e HiGHS plugável.

    O CBC vem junto com o PuLP e não exige instalação adicional, o que mantém o
    trabalho reprodutível em qualquer máquina do laboratório. O HiGHS é aceito
    para quem o tiver instalado (``pip install highspy``) e costuma ser bem mais
    rápido nestes modelos com muitos binários e big-M.
    """
    nome_normalizado = nome.strip().upper()
    if nome_normalizado in {"CBC", "PULP_CBC_CMD"}:
        return pulp.PULP_CBC_CMD(msg=msg, timeLimit=tempo_limite, **extras)
    if nome_normalizado in {"HIGHS", "HIGHS_CMD"}:
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

    O CBC só imprime ``Lower bound`` e ``Gap`` quando **não** prova otimalidade;
    quando prova, o limite inferior é o próprio objetivo e o gap é zero, e isso
    é tratado por quem chama.
    """
    if not caminho.exists():
        return None, None, ""
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    limite = gap = None
    if (achado := re.search(r"^Lower bound:\s*(-?[\d.eE+]+)", texto, re.M)):
        limite = float(achado.group(1))
    if (achado := re.search(r"^Gap:\s*(-?[\d.eE+]+)", texto, re.M)):
        gap = float(achado.group(1))
    mensagem = ""
    if (achado := re.search(r"^Result - (.+)$", texto, re.M)):
        mensagem = achado.group(1).strip()
    return limite, gap, mensagem


def resolver(
    inst: Instancia,
    cfg: ConfigModelo | None = None,
    tempo_limite: int | None = 300,
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
    solucao_encontrada = prob.status == pulp.LpStatusOptimal and any(
        var.value() is not None for var in variaveis.x.values()
    )

    # O CBC devolve status "Optimal" também quando para no limite de tempo com
    # uma incumbente; o log é a única fonte que distingue os dois casos.
    parou_no_tempo = "time limit" in mensagem.lower() or (
        gap_log is not None and gap_log > 1e-9
    )
    if status_bruto == "Optimal" and solucao_encontrada:
        status = STATUS_VIAVEL if parou_no_tempo else STATUS_OTIMO
    elif status_bruto == "Infeasible":
        status = STATUS_INVIAVEL
    elif status_bruto == "Not Solved":
        status = STATUS_VIAVEL if solucao_encontrada else STATUS_INDEFINIDO
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
            programacao=None,
            mensagem=mensagem or status_bruto,
        )

    objetivo_solver = pulp.value(prob.objective)
    programacao = extrair(inst, variaveis, cfg.penalidade_antecipacao)

    if status == STATUS_OTIMO:
        limite_inferior: float | None = objetivo_solver
        gap: float | None = 0.0
    else:
        limite_inferior = limite_log
        if gap_log is not None:
            gap = gap_log
        elif limite_inferior not in (None, 0) and objetivo_solver is not None:
            # Mesma convenção do CBC: gap relativo ao **limite inferior**, e não
            # ao incumbente. Por isso valores acima de 100% são normais quando o
            # limite ainda está fraco.
            gap = abs(objetivo_solver - limite_inferior) / abs(limite_inferior)
        else:
            gap = None

    divergencia = (
        None
        if objetivo_solver is None
        else programacao.objetivo - objetivo_solver
    )

    return Resultado(
        status=status,
        objetivo=objetivo_solver,
        limite_inferior=limite_inferior,
        gap=gap,
        tempo_s=tempo_s,
        n_variaveis=n_variaveis,
        n_restricoes=n_restricoes,
        programacao=programacao,
        divergencia_recalculo=divergencia,
        mensagem=mensagem or status_bruto,
    )
