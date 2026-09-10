"""Saída textual formatada e gráfico de Gantt.

É o único módulo autorizado a produzir saída visível: o resto do código devolve
dados, e quem decide como mostrá-los é aqui.

Duas convenções para o texto sobreviver ao console do Windows: as funções
``formatar_*`` devolvem ``str`` (para o chamador poder salvar em arquivo) e as
``imprimir_*`` escrevem; e a moldura das tabelas usa apenas ASCII, porque o
console padrão do Windows (cp1252) não codifica traços de caixa e levantaria
``UnicodeEncodeError`` no meio de um relatório.

Importa apenas :mod:`dados` em tempo de execução. O tipo ``Resultado`` de
:mod:`modelo` entra só sob ``TYPE_CHECKING``, para anotar as funções sem criar
acoplamento real com o solver.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from rubbertech.dados import Instancia, Programacao, Tarefa

if TYPE_CHECKING:  # pragma: no cover - apenas anotação
    from rubbertech.modelo import Resultado

#: Largura padrão das réguas horizontais.
LARGURA = 84
#: Tolerância ao contar itens atrasados (evita contar erro de arredondamento).
TOLERANCIA = 1e-6


def configurar_saida(stream: TextIO | None = None) -> None:
    """Coloca a saída em UTF-8 quando o terminal permite.

    Sem isto, um console em cp1252 exibe "programação" corrompido. É chamada
    pelo CLI, e não na importação, para não mexer no estado global de quem
    apenas importa a biblioteca.
    """
    alvos = [stream] if stream is not None else [sys.stdout, sys.stderr]
    for alvo in alvos:
        if (reconfigurar := getattr(alvo, "reconfigure", None)) is None:
            continue
        try:
            reconfigurar(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - terminal exótico
            pass


def _regua(caractere: str = "-", largura: int = LARGURA) -> str:
    return caractere * largura


def _numero(valor: float | None, casas: int = 2, vazio: str = "-") -> str:
    """Formata número com vírgula decimal; ``None`` vira um traço."""
    if valor is None:
        return vazio
    return f"{valor:,.{casas}f}".replace(",", " ").replace(".", ",")


def metricas(prog: Programacao, inst: Instancia | None = None) -> dict[str, object]:
    """Indicadores agregados de uma programação, para o relatório.

    ``atraso_ponderado`` exige ``inst`` (os pesos não estão na programação); sem
    ela usa ``prog.objetivo``, o que só coincide quando ``α = 0``.
    ``atraso_total`` (sem pesos) mostra que o ótimo ponderado concentra atraso
    em poucos itens baratos; ``ocupacao_por_linha`` expõe o desbalanceamento
    causado pela elegibilidade restrita.
    """
    makespan = max((t.fim for t in prog.tarefas), default=0.0)
    if inst is not None:
        atraso_ponderado = sum(inst.itens[t.item].w * t.atraso for t in prog.tarefas)
    else:
        atraso_ponderado = prog.objetivo

    grupos: dict[str, list[Tarefa]] = {linha: [] for linha in prog.sequencias}
    for tarefa in prog.tarefas:
        grupos.setdefault(tarefa.linha, []).append(tarefa)
    ocupacao = {
        linha: (
            sum((t.fim - t.inicio) + t.setup for t in tarefas) / makespan
            if makespan > 0
            else 0.0
        )
        for linha, tarefas in grupos.items()
    }

    return {
        "atraso_ponderado": atraso_ponderado,
        "atraso_total": sum(t.atraso for t in prog.tarefas),
        "n_atrasados": sum(1 for t in prog.tarefas if t.atraso > TOLERANCIA),
        "makespan": makespan,
        "tempo_total_setup": sum(t.setup for t in prog.tarefas),
        "ocupacao_por_linha": ocupacao,
    }


# ----------------------------------------------------------------------
# Instância
# ----------------------------------------------------------------------
def formatar_instancia(inst: Instancia) -> str:
    """Resumo da instância carregada, para o cabeçalho da execução."""
    com_cabo = sum(1 for item in inst.itens.values() if item.cabo_aco)
    return "\n".join(
        [
            _regua("="),
            "INSTÂNCIA",
            _regua("-"),
            f"itens ............... {inst.n} ({com_cabo} com cabo de aço)",
            f"linhas .............. {len(inst.M)}: {', '.join(inst.M)}",
            f"arcos válidos ....... {sum(1 for _ in inst.arcos())}",
            f"big-M calculado ..... {_numero(inst.big_m())}",
            _regua("="),
        ]
    )


# ----------------------------------------------------------------------
# Resultado da resolução
# ----------------------------------------------------------------------
#: Como cada status deve ser lido. A distinção entre as duas primeiras linhas é
#: a informação mais importante da saída inteira.
EXPLICACAO_STATUS = {
    "Optimal": "ótimo provado (o solver fechou o gap)",
    "Not Solved": "solução VIÁVEL no limite de tempo — NÃO é o ótimo provado",
    "Infeasible": "modelo inviável: nenhuma programação satisfaz as restrições",
    "Undefined": "o solver não devolveu solução utilizável",
}


def formatar_resultado(res: Resultado, divergencia: float | None = None) -> str:
    """Cabeçalho da resolução: status, objetivo, gap, tempo e tamanho do modelo.

    ``divergencia`` é a diferença entre o objetivo recalculado de forma
    independente e o do solver (ver :func:`conferencia.conferir`); deve ser ~0.
    """
    linhas = [
        _regua("="),
        "RESULTADO DA RESOLUÇÃO",
        _regua("="),
        f"status .............. {res.status}  "
        f"({EXPLICACAO_STATUS.get(res.status, '?')})",
        f"objetivo ............ {_numero(res.objetivo)}",
        f"limite inferior ..... {_numero(res.limite_inferior)}",
        f"gap ................. {_numero(res.gap_percentual)}%",
        f"tempo ............... {_numero(res.tempo_s)} s",
        f"tamanho do modelo ... {res.n_variaveis} variáveis, "
        f"{res.n_restricoes} restrições",
    ]
    if res.mensagem:
        linhas.append(f"mensagem do solver .. {res.mensagem}")
    if divergencia is not None:
        linhas.append(
            "conferência ......... objetivo recalculado de forma independente "
            f"difere em {_numero(divergencia, 6)}"
        )
    if res.status == "Not Solved":
        linhas += [
            "",
            "ATENÇÃO: o valor acima é um limitante superior. O ótimo está entre o",
            "limite inferior e o objetivo; o gap mede essa distância.",
        ]
    linhas.append(_regua("="))
    return "\n".join(linhas)


# ----------------------------------------------------------------------
# Programação
# ----------------------------------------------------------------------
def formatar_programacao(inst: Instancia, prog: Programacao) -> str:
    """Programação linha a linha, com a conta de cada item aberta.

    Para cada item mostra o setup pago, a janela de processamento, o prazo, o
    peso e o atraso — é assim que se confere na mão por que o ótimo escolheu
    atrasar um item e não outro.
    """
    linhas = [_regua("="), "PROGRAMAÇÃO DA PRODUÇÃO", _regua("=")]
    cabecalho = (
        f"{'#':>2}  {'item':<8} {'setup':>7} {'início':>8} {'fim':>8} "
        f"{'prazo':>8} {'peso':>5} {'atraso':>8}  situação"
    )

    for linha in inst.linhas:
        tarefas = prog.tarefas_da_linha(linha)
        sequencia = " -> ".join(t.item for t in tarefas) if tarefas else "(ociosa)"
        linhas += ["", f"Linha {linha}: {sequencia}"]
        if not tarefas:
            continue
        linhas += [_regua("-"), cabecalho, _regua("-")]
        for ordem, tarefa in enumerate(tarefas, start=1):
            item = inst.itens[tarefa.item]
            situacao = "ATRASO" if tarefa.atraso > 1e-9 else "no prazo"
            linhas.append(
                f"{ordem:>2}  {tarefa.item:<8} {_numero(tarefa.setup, 1):>7} "
                f"{_numero(tarefa.inicio, 1):>8} {_numero(tarefa.fim, 1):>8} "
                f"{_numero(item.d, 1):>8} {_numero(item.w, 1):>5} "
                f"{_numero(tarefa.atraso, 1):>8}  {situacao}"
            )

    ind = metricas(prog, inst)
    ocupacao = ind["ocupacao_por_linha"]
    assert isinstance(ocupacao, dict)
    linhas += [
        "",
        _regua("="),
        "INDICADORES",
        _regua("-"),
        f"atraso ponderado (objetivo) . {_numero(ind['atraso_ponderado'])}",
        f"atraso total (sem pesos) .... {_numero(ind['atraso_total'])}",
        f"itens atrasados ............. {ind['n_atrasados']} de {inst.n}",
        f"makespan .................... {_numero(ind['makespan'])}",
        f"tempo total de setup ........ {_numero(ind['tempo_total_setup'])}",
        "ocupação por linha .......... "
        + "  ".join(f"{k}={_numero(100 * v, 1)}%" for k, v in ocupacao.items()),
        _regua("="),
    ]
    return "\n".join(linhas)


def formatar_violacoes(violacoes: list[str]) -> str:
    """Resultado da verificação independente, em texto."""
    if not violacoes:
        return "VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada."
    return "\n".join(
        [f"VERIFICAÇÃO INDEPENDENTE: {len(violacoes)} violação(ões)!"]
        + [f"  - {violacao}" for violacao in violacoes]
    )


def imprimir(texto: str, arquivo: TextIO | None = None) -> None:
    """Escreve um bloco já formatado."""
    print(texto, file=arquivo or sys.stdout)


# ----------------------------------------------------------------------
# Gráfico de Gantt
# ----------------------------------------------------------------------
#: Fração da altura da barra usada pelo bloco de setup, e sua transparência.
ALTURA_BARRA = 0.55
ALFA_SETUP = 0.35


def gantt(
    inst: Instancia,
    prog: Programacao,
    caminho: str | Path | None = None,
    titulo: str | None = None,
    mostrar: bool = False,
) -> Any:
    """Desenha o Gantt da programação e devolve a figura.

    Cada item vira duas faixas: o setup (translúcido) e o processamento
    (sólido). O prazo aparece como marcador vertical na altura da linha, e os
    itens atrasados recebem borda destacada e hachura — assim o atraso é
    identificável mesmo em impressão em preto e branco. As cores saem do ciclo
    ativo do matplotlib, e não de uma lista fixa, para o gráfico acompanhar o
    estilo escolhido por quem gerar as figuras.
    """
    import matplotlib

    if caminho is not None and not mostrar:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ciclo = matplotlib.rcParams["axes.prop_cycle"].by_key().get("color", [])
    if len(ciclo) < 2:  # pragma: no cover - estilo sem ciclo de cores
        ciclo = ["C0", "C1"]
    cores = {False: ciclo[0], True: ciclo[1 % len(ciclo)]}

    linhas = list(inst.linhas)
    posicao = {linha: indice for indice, linha in enumerate(linhas)}
    figura, eixo = plt.subplots(figsize=(11, 1.1 * len(linhas) + 2.2))

    for linha in linhas:
        y = posicao[linha]
        for tarefa in prog.tarefas_da_linha(linha):
            item = inst.itens[tarefa.item]
            atrasado = tarefa.atraso > 1e-9
            eixo.barh(
                y,
                tarefa.setup,
                left=tarefa.inicio - tarefa.setup,
                height=ALTURA_BARRA,
                color=cores[item.cabo_aco],
                alpha=ALFA_SETUP,
                edgecolor="none",
            )
            eixo.barh(
                y,
                tarefa.fim - tarefa.inicio,
                left=tarefa.inicio,
                height=ALTURA_BARRA,
                color=cores[item.cabo_aco],
                edgecolor="black" if atrasado else "none",
                linewidth=1.4 if atrasado else 0.0,
                hatch="//" if atrasado else None,
            )
            eixo.text(
                (tarefa.inicio + tarefa.fim) / 2, y, tarefa.item,
                ha="center", va="center", fontsize=8,
            )
            eixo.plot(
                [item.d, item.d],
                [y - ALTURA_BARRA / 2 - 0.08, y + ALTURA_BARRA / 2 + 0.08],
                linestyle=":", linewidth=1.2, color="black",
            )

    ind = metricas(prog, inst)
    eixo.set_yticks(list(posicao.values()))
    eixo.set_yticklabels(linhas)
    eixo.invert_yaxis()
    eixo.set_xlabel("tempo (u.t.)")
    eixo.set_xlim(left=0)
    eixo.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.6)
    eixo.set_title(
        titulo
        or f"Programação — atraso ponderado {ind['atraso_ponderado']:.1f}, "
        f"{ind['n_atrasados']} item(ns) atrasado(s)"
    )
    eixo.legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color=cores[False], label="têxtil"),
            plt.Rectangle((0, 0), 1, 1, color=cores[True], label="cabo de aço"),
            plt.Rectangle(
                (0, 0), 1, 1, facecolor="white", edgecolor="black", hatch="//",
                label="atrasado",
            ),
            plt.Line2D([0], [0], linestyle=":", color="black", label="prazo"),
        ],
        loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, frameon=False,
    )
    figura.tight_layout()

    if caminho is not None:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        figura.savefig(destino, dpi=150, bbox_inches="tight")
    if mostrar:  # pragma: no cover - interativo
        plt.show()
    return figura
