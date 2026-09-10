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
import textwrap
from collections.abc import Sequence
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
        limite_txt = (
            f"{res.tempo_limite} s" if res.tempo_limite is not None else "configurado"
        )
        # Destacado com régua própria: é a informação mais fácil de passar
        # despercebida na saída inteira — sem ela, "Not Solved" com um objetivo
        # preenchido parece, à primeira vista, uma solução como outra qualquer.
        linhas += [
            "",
            _regua("!"),
            f"ATENÇÃO: atingiu o limite de {limite_txt}: a solução abaixo é VIÁVEL,",
            "mas NÃO é comprovadamente ótima. O ótimo verdadeiro está entre o",
            "limite inferior e o objetivo mostrados acima; o gap mede essa",
            "distância. Para tentar fechar o gap, use --tempo-limite com um valor",
            "maior (ver 'Como alterar o limite de tempo do solver' no README).",
            _regua("!"),
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


# ----------------------------------------------------------------------
# Legenda: campos de entrada e indicadores de saída
# ----------------------------------------------------------------------
# Fonte única desta informação: o texto aqui é reproduzido, quase literalmente,
# em `dados/COMO_PREENCHER.md`. Não repita este conteúdo em outro lugar do
# projeto (README incluído) — aponte para `python main.py legenda` ou para o
# arquivo. Ver seção 5 do README.

#: (campo, símbolo na formulação, o que significa, unidade, obrigatório, exemplo)
CAMPOS_ENTRADA: list[tuple[str, str, str, str, str, str]] = [
    (
        "nome",
        "—",
        "rótulo da instância; só identificação, não entra no modelo",
        "—",
        "não (padrão 'instancia')",
        '"referencia"',
    ),
    (
        "no_inicial",
        "0 (nó fictício)",
        "rótulo do nó fictício de início de linha; não pode coincidir com o id de um item",
        "—",
        "não (padrão 'INI')",
        '"INI"',
    ),
    (
        "linhas",
        "M",
        "nomes das linhas de produção",
        "—",
        "sim",
        '["L1", "L2"]',
    ),
    (
        "itens[].id",
        "i ∈ J",
        "identificador único do item",
        "—",
        "sim",
        '"TX1"',
    ),
    (
        "itens[].p",
        "p[i,k]",
        "tempo de processamento por linha ELEGÍVEL; a linha ausente diz 'não roda aqui'",
        "tempo (livre)",
        "sim",
        '{"L1": 20, "L2": 24}',
    ),
    (
        "itens[].d",
        "d[i]",
        "prazo de entrega, contado a partir de zero",
        "tempo (= unidade de p)",
        "sim",
        "30",
    ),
    (
        "itens[].w",
        "w[i]",
        "peso do atraso (multa contratual x criticidade do cliente)",
        "adimensional",
        "sim",
        "5",
    ),
    (
        "itens[].cabo_aco",
        "—",
        "rótulo de família para relatório e Gantt; NÃO restringe elegibilidade",
        "—",
        "não (padrão false)",
        "true",
    ),
    (
        "setup",
        "s[i,j]",
        "preparação para produzir j logo após i; indexado por (anterior, seguinte)",
        "tempo (= unidade de p e d)",
        "sim",
        '{"INI": {"TX1": 8}, "TX1": {"TX2": 5}}',
    ),
]

#: Cinco pontos que costumam causar erro — texto corrido, e não tabela, porque
#: são explicações e não campos.
NOTAS_ENTRADA: list[str] = [
    "'p' só lista as linhas ELEGÍVEIS. É a omissão de uma linha dentro de 'p' "
    "que impede o item de ser produzido nela — não existe uma lista separada de "
    "restrições. O campo 'cabo_aco' é apenas rótulo para os relatórios e não "
    "restringe nada.",
    "'setup' é indexado por par ORDENADO (item anterior, item seguinte), e não "
    "precisa ser simétrico: setup[\"TX1\"][\"CA1\"] pode (e costuma) diferir de "
    "setup[\"CA1\"][\"TX1\"]. É essa assimetria que representa montar contra "
    "desmontar o dispositivo de tração dos cabos.",
    "A chave \"INI\" (ou o valor de 'no_inicial') guarda o setup INICIAL de cada "
    "linha, aplicado ao primeiro item produzido nela.",
    "Unidades de tempo são livres, desde que CONSISTENTES entre 'p', 'setup' e "
    "'d'. Se 'p' está em horas, 'd' precisa estar em horas — misturar unidades "
    "não dá erro de validação, só resultado sem sentido.",
    "'w' é adimensional e só a PROPORÇÃO entre os pesos importa: dobrar todos "
    "os pesos dobra o objetivo sem mudar a programação ótima.",
]

#: (indicador, formato, o que significa)
CAMPOS_SAIDA_RESULTADO: list[tuple[str, str, str]] = [
    (
        "status",
        "Optimal | Not Solved | Infeasible | Undefined",
        "Optimal = ótimo provado (gap = 0). Not Solved = o solver parou no limite "
        "de tempo com uma solução VIÁVEL na mão — o objetivo é um limitante "
        "superior, não o ótimo. Infeasible = nenhuma programação satisfaz as "
        "restrições. Undefined = o solver não devolveu nada utilizável.",
    ),
    (
        "objetivo",
        "número, ou '-'",
        "valor de Σ w_i·T_i (mais Σ α_i·A_i se --alfa > 0) da melhor solução "
        "encontrada; '-' quando não há solução (status Infeasible/Undefined).",
    ),
    (
        "limite inferior",
        "número, ou '-'",
        "melhor limitante inferior provado pelo branch-and-bound; igual ao "
        "objetivo quando status = Optimal.",
    ),
    (
        "gap",
        "porcentagem, ou '-'",
        "(objetivo − limite inferior) / limite inferior, em %. Zero = ótimo "
        "provado. INDEFINIDO ('-' na tela) quando o limite inferior é 0: falta "
        "de informação sobre a qualidade da solução, e não indício de solução "
        "ruim.",
    ),
    (
        "tempo",
        "segundos",
        "tempo de parede da resolução, incluindo a construção do modelo — não é "
        "o --tempo-limite pedido, é o que a execução de fato levou.",
    ),
    (
        "tamanho do modelo",
        "N variáveis, N restrições",
        "quantidade efetivamente gerada pelo modelo para esta instância "
        "(depende da elegibilidade: linhas inelegíveis não geram variável).",
    ),
    (
        "conferência",
        "número (diferença)",
        "objetivo recalculado do zero pelo avaliador independente menos o "
        "objetivo do solver; deve ser ~0. Só aparece quando há programação.",
    ),
]

#: (coluna da tabela de programação, símbolo, o que significa)
CAMPOS_SAIDA_PROGRAMACAO: list[tuple[str, str, str]] = [
    (
        "setup",
        "s[anterior, item]",
        "preparação paga ANTES deste item, referente ao par (item anterior, "
        "este item); no primeiro item da linha é o setup inicial (s[INI, i]).",
    ),
    (
        "início / fim",
        "C_i (janela)",
        "janela de processamento do item, já depois do setup: o setup ocupa de "
        "'início - setup' até 'início'.",
    ),
    ("prazo", "d_i", "prazo de entrega do item."),
    ("peso", "w_i", "peso do atraso do item."),
    (
        "atraso",
        "T_i",
        "T_i = max(0, fim - prazo); a coluna 'situação' mostra 'ATRASO' quando "
        "T_i > 0, 'no prazo' caso contrário.",
    ),
]


def _tabela(
    cabecalhos: Sequence[str],
    linhas: Sequence[Sequence[str]],
    larguras_max: Sequence[int | None] | None = None,
) -> str:
    """Tabela ASCII de largura variável — sem unicode de caixa, mesma razão do
    resto do módulo. Colunas sem `larguras_max` usam a largura do maior valor;
    colunas com um limite quebram o texto em várias linhas dentro da célula, em
    vez de produzir uma tabela larga demais para caber num terminal comum.
    """
    n_colunas = len(cabecalhos)
    limites = list(larguras_max) if larguras_max is not None else [None] * n_colunas

    def _celulas(valor: str, limite: int | None) -> list[str]:
        texto = str(valor)
        if limite is None or len(texto) <= limite:
            return [texto]
        return textwrap.wrap(texto, width=limite) or [""]

    linhas_quebradas = [
        [_celulas(valor, limites[c]) for c, valor in enumerate(linha)] for linha in linhas
    ]
    larguras = [
        max(
            len(str(cabecalhos[c])),
            max(
                (len(parte) for linha in linhas_quebradas for parte in linha[c]),
                default=0,
            ),
        )
        for c in range(n_colunas)
    ]

    def _linha(valores: Sequence[str]) -> str:
        return "  ".join(str(v).ljust(larguras[i]) for i, v in enumerate(valores))

    corpo = [_linha(cabecalhos), _regua("-", sum(larguras) + 2 * (n_colunas - 1))]
    for linha in linhas_quebradas:
        for indice in range(max(len(coluna) for coluna in linha)):
            corpo.append(
                _linha([coluna[indice] if indice < len(coluna) else "" for coluna in linha])
            )
    return "\n".join(corpo)


def formatar_legenda_entrada() -> str:
    """Tabela de campos do JSON de entrada, com as notas que evitam erro comum."""
    linhas = [
        _regua("="),
        "LEGENDA — CAMPOS DE ENTRADA (arquivo JSON)",
        _regua("="),
        _tabela(
            ["campo", "símbolo", "o que significa", "unidade", "obrigatório", "exemplo"],
            CAMPOS_ENTRADA,
            larguras_max=[None, None, 42, 20, None, None],
        ),
        "",
        "Pontos que costumam causar erro:",
    ]
    linhas += [f"  {n + 1}. {nota}" for n, nota in enumerate(NOTAS_ENTRADA)]
    linhas += [
        "",
        "Exemplo completo e guia de preenchimento: dados/COMO_PREENCHER.md",
        _regua("="),
    ]
    return "\n".join(linhas)


def formatar_legenda_saida() -> str:
    """Tabela dos indicadores do bloco RESULTADO e das colunas da programação."""
    linhas = [
        _regua("="),
        "LEGENDA — INDICADORES DE SAÍDA",
        _regua("="),
        "Bloco RESULTADO DA RESOLUÇÃO:",
        _tabela(
            ["indicador", "formato", "o que significa"],
            CAMPOS_SAIDA_RESULTADO,
            larguras_max=[None, None, 46],
        ),
        "",
        "Colunas da tabela de PROGRAMAÇÃO:",
        _tabela(
            ["coluna", "símbolo", "o que significa"],
            CAMPOS_SAIDA_PROGRAMACAO,
            larguras_max=[None, None, 46],
        ),
        "",
        "Dois pontos que costumam ser lidos errado:",
        "  1. status = 'Not Solved' com objetivo preenchido é uma solução VIÁVEL,",
        "     não a ótima — o objetivo é um limitante superior.",
        "  2. gap indefinido ('-', quando o limite inferior é 0) significa AUSÊNCIA",
        "     de informação sobre a qualidade da solução, não solução ruim.",
        _regua("="),
    ]
    return "\n".join(linhas)


def formatar_legenda(entrada: bool = True, saida: bool = True) -> str:
    """Junta as duas legendas, respeitando quais foram pedidas."""
    blocos = []
    if entrada:
        blocos.append(formatar_legenda_entrada())
    if saida:
        blocos.append(formatar_legenda_saida())
    return "\n\n".join(blocos)


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
