"""Gráfico de Gantt da programação.

Junto com :mod:`rubbertech.relatorio`, é o único módulo do pacote que produz
saída visível. As cores saem do ciclo de cores ativo do matplotlib, e não de uma
lista fixa no código: assim o gráfico acompanha o estilo escolhido por quem for
gerar as figuras do relatório, e um item com cabo de aço não fica preso a um
"azul" arbitrário.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

from rubbertech.dominio import Instancia, Programacao
from rubbertech.solucao import metricas

#: Fração da altura da barra usada pelo bloco de setup.
ALTURA_BARRA = 0.55
#: Transparência do bloco de setup, para distingui-lo do processamento.
ALFA_SETUP = 0.35


def _cores_por_familia(inst: Instancia) -> dict[bool, Any]:
    """Duas cores do ciclo ativo: uma para têxtil, outra para cabo de aço."""
    ciclo = matplotlib.rcParams["axes.prop_cycle"].by_key().get("color", [])
    if len(ciclo) < 2:  # pragma: no cover - estilo sem ciclo de cores
        ciclo = ["C0", "C1"]
    return {False: ciclo[0], True: ciclo[1 % len(ciclo)]}


def gantt(
    inst: Instancia,
    prog: Programacao,
    caminho: str | Path | None = None,
    titulo: str | None = None,
    mostrar: bool = False,
) -> Any:
    """Desenha o Gantt da programação e devolve a figura.

    Cada item vira duas faixas: o setup (translúcido) e o processamento
    (sólido). O prazo aparece como um marcador vertical na altura da linha, e os
    itens atrasados recebem borda destacada e hachura — assim o atraso é
    identificável mesmo em impressão em preto e branco.

    Com ``caminho``, salva o arquivo (o formato vem da extensão) usando o
    backend não interativo; sem ``caminho`` e com ``mostrar=True``, abre a
    janela.
    """
    if caminho is not None and not mostrar:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cores = _cores_por_familia(inst)
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
                (tarefa.inicio + tarefa.fim) / 2,
                y,
                tarefa.item,
                ha="center",
                va="center",
                fontsize=8,
            )
            eixo.plot(
                [item.d, item.d],
                [y - ALTURA_BARRA / 2 - 0.08, y + ALTURA_BARRA / 2 + 0.08],
                linestyle=":",
                linewidth=1.2,
                color="black",
            )

    indicadores = metricas(prog, inst)
    eixo.set_yticks(list(posicao.values()))
    eixo.set_yticklabels(linhas)
    eixo.invert_yaxis()
    eixo.set_xlabel("tempo (u.t.)")
    eixo.set_xlim(left=0)
    eixo.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.6)
    eixo.set_title(
        titulo
        or (
            f"Programação — atraso ponderado "
            f"{indicadores['atraso_ponderado']:.1f}, "
            f"{indicadores['n_atrasados']} item(ns) atrasado(s)"
        )
    )

    legenda = [
        plt.Rectangle((0, 0), 1, 1, color=cores[False], label="têxtil"),
        plt.Rectangle((0, 0), 1, 1, color=cores[True], label="cabo de aço"),
        plt.Rectangle(
            (0, 0), 1, 1, facecolor="white", edgecolor="black", hatch="//",
            label="atrasado",
        ),
        plt.Line2D([0], [0], linestyle=":", color="black", label="prazo"),
    ]
    eixo.legend(
        handles=legenda, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4,
        frameon=False,
    )
    figura.tight_layout()

    if caminho is not None:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        figura.savefig(destino, dpi=150, bbox_inches="tight")
    if mostrar:  # pragma: no cover - interativo
        plt.show()
    return figura
