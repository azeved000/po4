"""Saída textual formatada.

Junto com :mod:`rubbertech.visual`, este é o único lugar do pacote autorizado a
escrever na tela. O resto do código devolve dados; quem decide como mostrá-los é
aqui.

Duas convenções para o texto sobreviver ao console do Windows: as funções
``formatar_*`` devolvem ``str`` (para o script poder salvar em arquivo) e as
``imprimir_*`` escrevem; e a moldura das tabelas usa apenas caracteres ASCII,
porque o console padrão do Windows (cp1252) não codifica traços de caixa e
levantaria ``UnicodeEncodeError`` no meio de um relatório.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

from rubbertech.dominio import Instancia, Programacao
from rubbertech.solucao import metricas

if TYPE_CHECKING:  # pragma: no cover - apenas anotação
    from rubbertech.solver import Resultado

#: Largura padrão das réguas horizontais.
LARGURA = 84


def configurar_saida(stream: TextIO | None = None) -> None:
    """Coloca a saída em UTF-8 quando o terminal permite.

    Sem isto, um console em cp1252 exibe "programação" corrompido. Sem argumento,
    ajusta ``stdout`` e ``stderr`` — as mensagens de erro de instância inválida
    saem por ``stderr`` e precisam ser legíveis tanto quanto o relatório.

    É chamada pelos scripts de linha de comando, e não na importação do módulo,
    para não mexer no estado global de quem apenas importa a biblioteca.
    """
    alvos = [stream] if stream is not None else [sys.stdout, sys.stderr]
    for alvo in alvos:
        reconfigurar = getattr(alvo, "reconfigure", None)
        if reconfigurar is None:
            continue
        try:
            reconfigurar(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - terminal exótico
            pass


def _regua(caractere: str = "-", largura: int = LARGURA) -> str:
    return caractere * largura


def _numero(valor: float | None, casas: int = 2, vazio: str = "-") -> str:
    """Formata número no padrão brasileiro (1.234,56); ``None`` vira um traço."""
    if valor is None:
        return vazio
    return (
        f"{valor:,.{casas}f}"
        .replace(",", "\x00")  # separador de milhar, provisório
        .replace(".", ",")  # decimal
        .replace("\x00", ".")  # milhar definitivo
    )


# ----------------------------------------------------------------------
# Programação
# ----------------------------------------------------------------------
def formatar_programacao(inst: Instancia, prog: Programacao) -> str:
    """Programação linha a linha, com a conta de cada item aberta.

    Para cada item mostra o setup pago, a janela de processamento, o prazo, o
    peso e o atraso — é assim que se confere na mão por que o ótimo escolheu
    atrasar um item e não outro.
    """
    linhas_texto: list[str] = []
    linhas_texto.append(_regua("="))
    linhas_texto.append("PROGRAMAÇÃO DA PRODUÇÃO")
    linhas_texto.append(_regua("="))

    mostra_cliente = any(item.cliente for item in inst.itens.values())
    coluna_cliente = f" {'cliente':<20}" if mostra_cliente else ""
    cabecalho = (
        f"{'#':>2}  {'item':<8} {'setup':>7} {'início':>8} {'fim':>8} "
        f"{'prazo':>8} {'peso':>5} {'atraso':>8}{coluna_cliente}  situação"
    )

    for linha in inst.linhas:
        tarefas = prog.tarefas_da_linha(linha)
        sequencia = " -> ".join(t.item for t in tarefas) if tarefas else "(ociosa)"
        linhas_texto.append("")
        linhas_texto.append(f"Linha {linha}: {sequencia}")
        if not tarefas:
            continue
        linhas_texto.append(_regua("-"))
        linhas_texto.append(cabecalho)
        linhas_texto.append(_regua("-"))
        for ordem, tarefa in enumerate(tarefas, start=1):
            item = inst.itens[tarefa.item]
            situacao = "ATRASO" if tarefa.atraso > 1e-9 else "no prazo"
            cliente = f" {item.cliente:<20}" if mostra_cliente else ""
            linhas_texto.append(
                f"{ordem:>2}  {tarefa.item:<8} {_numero(tarefa.setup, 1):>7} "
                f"{_numero(tarefa.inicio, 1):>8} {_numero(tarefa.fim, 1):>8} "
                f"{_numero(item.d, 1):>8} {_numero(item.w, 1):>5} "
                f"{_numero(tarefa.atraso, 1):>8}{cliente}  {situacao}"
            )

    indicadores = metricas(prog, inst)
    linhas_texto.append("")
    linhas_texto.append(_regua("="))
    linhas_texto.append("INDICADORES")
    linhas_texto.append(_regua("-"))
    linhas_texto.append(
        f"atraso ponderado (objetivo) . {_numero(indicadores['atraso_ponderado'])}"
    )
    linhas_texto.append(
        f"atraso total (sem pesos) .... {_numero(indicadores['atraso_total'])}"
    )
    linhas_texto.append(
        f"itens atrasados ............. {indicadores['n_atrasados']} de {inst.n}"
    )
    linhas_texto.append(
        f"makespan .................... {_numero(indicadores['makespan'])}"
    )
    linhas_texto.append(
        f"tempo total de setup ........ {_numero(indicadores['tempo_total_setup'])}"
    )
    ocupacao = indicadores["ocupacao_por_linha"]
    assert isinstance(ocupacao, dict)
    detalhe = "  ".join(
        f"{linha}={_numero(100 * valor, 1)}%" for linha, valor in ocupacao.items()
    )
    linhas_texto.append(f"ocupação por linha .......... {detalhe}")
    linhas_texto.append(_regua("="))

    if mostra_cliente:
        linhas_texto.append("")
        linhas_texto.append(formatar_por_cliente(inst, prog))
    return "\n".join(linhas_texto)


def formatar_por_cliente(inst: Instancia, prog: Programacao) -> str:
    """Atraso agregado por cliente, do mais penalizado para o menos.

    O objetivo é uma soma sobre itens, mas quem cobra é o cliente. Esta tabela é
    a tradução: mostra em quem o atraso caiu, quantos pedidos ele tem e quanto
    do objetivo total veio dele. É também a conferência mais rápida de que a
    ponderação está funcionando — o cliente de maior peso deve aparecer com
    pouco ou nenhum atraso.
    """
    agregado: dict[str, dict[str, float]] = {}
    for tarefa in prog.tarefas:
        item = inst.itens[tarefa.item]
        registro = agregado.setdefault(
            item.cliente, {"pedidos": 0.0, "atrasados": 0.0, "atraso": 0.0,
                           "ponderado": 0.0, "peso": item.w}
        )
        registro["pedidos"] += 1
        registro["atraso"] += tarefa.atraso
        registro["ponderado"] += item.w * tarefa.atraso
        if tarefa.atraso > 1e-9:
            registro["atrasados"] += 1

    linhas_texto = [
        _regua("="),
        "ATRASO POR CLIENTE",
        _regua("-"),
        f"{'cliente':<22} {'peso':>5} {'pedidos':>8} {'atrasados':>10} "
        f"{'atraso':>10} {'contribuição':>13}",
        _regua("-"),
    ]
    ordenado = sorted(
        agregado.items(), key=lambda par: (-par[1]["ponderado"], par[0])
    )
    for cliente, dados in ordenado:
        linhas_texto.append(
            f"{cliente or '(sem cliente)':<22} {_numero(dados['peso'], 1):>5} "
            f"{int(dados['pedidos']):>8} {int(dados['atrasados']):>10} "
            f"{_numero(dados['atraso'], 1):>10} "
            f"{_numero(dados['ponderado'], 1):>13}"
        )
    linhas_texto.append(_regua("="))
    return "\n".join(linhas_texto)


def imprimir_programacao(
    inst: Instancia, prog: Programacao, arquivo: TextIO | None = None
) -> None:
    """Escreve a programação formatada."""
    print(formatar_programacao(inst, prog), file=arquivo or sys.stdout)


# ----------------------------------------------------------------------
# Resultado da resolução
# ----------------------------------------------------------------------
#: Como cada status deve ser lido no relatório. A distinção entre as duas
#: primeiras linhas é a informação mais importante da saída inteira.
EXPLICACAO_STATUS = {
    "Optimal": "ótimo provado (o solver fechou o gap)",
    "Not Solved": "solução VIÁVEL no limite de tempo — NÃO é o ótimo provado",
    "Infeasible": "modelo inviável: nenhuma programação satisfaz as restrições",
    "Undefined": "o solver não devolveu solução utilizável",
}


def formatar_resultado(res: "Resultado") -> str:
    """Cabeçalho da resolução: status, objetivo, gap, tempo e tamanho do modelo."""
    linhas_texto = [
        _regua("="),
        "RESULTADO DA RESOLUÇÃO",
        _regua("="),
        f"status .............. {res.status}  ({EXPLICACAO_STATUS.get(res.status, '?')})",
        f"objetivo ............ {_numero(res.objetivo)}",
        f"limite inferior ..... {_numero(res.limite_inferior)}",
        f"gap ................. "
        + (
            "indefinido (limite inferior nulo)"
            if res.gap is None and res.limite_inferior is not None
            else f"{_numero(None if res.gap is None else 100 * res.gap)}%"
        ),
        f"tempo ............... {_numero(res.tempo_s)} s",
        f"tamanho do modelo ... {res.n_variaveis} variáveis, "
        f"{res.n_restricoes} restrições",
    ]
    if res.mensagem:
        linhas_texto.append(f"mensagem do solver .. {res.mensagem}")
    if res.divergencia_recalculo is not None:
        linhas_texto.append(
            f"conferência ......... objetivo recalculado de forma independente "
            f"difere em {_numero(res.divergencia_recalculo, 6)}"
        )
    if res.status == "Not Solved":
        linhas_texto.append("")
        linhas_texto.append(
            "ATENÇÃO: o valor acima é um limitante superior, não o ótimo."
        )
        if res.gap is None:
            linhas_texto.append(
                "Sem limite inferior útil, não há como afirmar quão longe do"
            )
            linhas_texto.append(
                "ótimo ele está. Aumente --tempo-limite para estreitar a faixa."
            )
        else:
            linhas_texto.append(
                "O ótimo está entre o limite inferior e o objetivo; o gap mede"
            )
            linhas_texto.append("essa distância.")
    linhas_texto.append(_regua("="))
    return "\n".join(linhas_texto)


def imprimir_resultado(res: "Resultado", arquivo: TextIO | None = None) -> None:
    """Escreve o resultado formatado."""
    print(formatar_resultado(res), file=arquivo or sys.stdout)


# ----------------------------------------------------------------------
# Tabelas comparativas (experimentos)
# ----------------------------------------------------------------------
def tabela_comparativa(resultados: dict[str, "Resultado"]) -> str:
    """Uma linha por configuração testada, para as tabelas do relatório."""
    cabecalho = (
        f"{'configuração':<22} {'status':<12} {'objetivo':>12} {'lim. inf.':>12} "
        f"{'gap %':>8} {'tempo s':>9} {'vars':>7} {'restr':>7}"
    )
    linhas_texto = [_regua("="), cabecalho, _regua("-")]
    for nome, res in resultados.items():
        linhas_texto.append(
            f"{nome:<22} {res.status:<12} {_numero(res.objetivo):>12} "
            f"{_numero(res.limite_inferior):>12} "
            f"{_numero(None if res.gap is None else 100 * res.gap, 1):>8} "
            f"{_numero(res.tempo_s, 1):>9} {res.n_variaveis:>7} "
            f"{res.n_restricoes:>7}"
        )
    linhas_texto.append(_regua("="))
    return "\n".join(linhas_texto)


def imprimir_tabela_comparativa(
    resultados: dict[str, "Resultado"], arquivo: TextIO | None = None
) -> None:
    """Escreve a tabela comparativa."""
    print(tabela_comparativa(resultados), file=arquivo or sys.stdout)


def formatar_instancia(inst: Instancia) -> str:
    """Resumo da instância carregada, para o cabeçalho da execução."""
    com_cabo = sum(1 for item in inst.itens.values() if item.cabo_aco)
    n_arcos = sum(1 for _ in inst.arcos())
    return "\n".join(
        [
            _regua("="),
            "INSTÂNCIA",
            _regua("-"),
            f"itens ............... {inst.n} ({com_cabo} com cabo de aço)",
            f"linhas .............. {len(inst.M)}: {', '.join(inst.M)}",
            f"arcos válidos ....... {n_arcos}",
            f"big-M calculado ..... {_numero(inst.big_m())}",
            _regua("="),
        ]
    )


def imprimir_instancia(inst: Instancia, arquivo: TextIO | None = None) -> None:
    """Escreve o resumo da instância."""
    print(formatar_instancia(inst), file=arquivo or sys.stdout)


def formatar_violacoes(violacoes: list[str]) -> str:
    """Resultado da verificação independente, em texto."""
    if not violacoes:
        return "VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada."
    linhas_texto = [f"VERIFICAÇÃO INDEPENDENTE: {len(violacoes)} violação(ões)!"]
    linhas_texto += [f"  - {violacao}" for violacao in violacoes]
    return "\n".join(linhas_texto)


def imprimir_violacoes(violacoes: list[str], arquivo: TextIO | None = None) -> None:
    """Escreve o resultado da verificação independente."""
    print(formatar_violacoes(violacoes), file=arquivo or sys.stdout)
