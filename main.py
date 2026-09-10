"""Ponto de entrada único do projeto RubberTech.

Três subcomandos::

    python main.py resolver --instancia referencia
    python main.py validar
    python main.py experimentos --experimento todos

``resolver``
    resolve uma instância por PLI, imprime o relatório e **confere a solução de
    forma independente** (o objetivo é recalculado fora do solver).
``validar``
    validação incremental: quatro estágios pequenos, cada um isolando um aspecto
    do modelo, confrontados com a enumeração exaustiva.
``experimentos``
    bateria de escala, MTZ e comparação com EDD, gravando CSV em ``resultados/``.

Este é o único módulo que importa todos os demais.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from rubbertech import dados, relatorio
from rubbertech.conferencia import conferir, edd, forca_bruta
from rubbertech.dados import Instancia, InstanciaInvalida
from rubbertech.modelo import (
    TEMPO_LIMITE_PADRAO,
    ConfigModelo,
    Resultado,
    resolver,
)

#: Diretórios de dados e de saída, relativos à raiz do projeto.
RAIZ = Path(__file__).resolve().parent
PASTA_RESULTADOS = RAIZ / "resultados"

#: Tolerância na comparação entre solver e enumeração. Folgada de propósito: o
#: CBC devolve valores com erro de arredondamento, e o que se quer detectar aqui
#: é discrepância estrutural, não o último bit.
TOLERANCIA = 1e-4

#: Tamanhos da bateria de escala. O suficiente para mostrar onde o CBC deixa de
#: provar otimalidade, sem uma hora de execução.
TAMANHOS = [6, 8, 10, 20, 80]
#: Sementes por tamanho nos experimentos de MTZ e de EDD. Uma execução só não
#: permite concluir nada sobre uma instância aleatória.
SEMENTES = [6, 7, 8]


# ======================================================================
# Carregamento de instâncias
# ======================================================================
#: Estágios da validação incremental, como combinações de argumentos de
#: :func:`dados.gerar`. Ver a tabela equivalente no README.
def estagios(n: int, seed: int) -> list[tuple[str, str, Instancia]]:
    """Os quatro estágios, com o que cada um se propõe a validar."""
    return [
        (
            "estágio 1",
            "uma linha, sem setup",
            dados.gerar(n, m=1, frac_cabo=0.0, com_setup=False, seed=seed),
        ),
        (
            "estágio 2",
            "uma linha, setup assimétrico",
            dados.gerar(n, m=1, frac_cabo=0.4, seed=seed + 1),
        ),
        (
            "estágio 3",
            "armadilha de subciclo",
            dados.gerar(
                n,
                m=1,
                frac_cabo=0.4,
                seed=seed + 2,
                armadilha_subciclo=dados.SETUP_INICIAL_ARMADILHA,
            ),
        ),
        (
            "estágio 4",
            "elegibilidade restrita",
            dados.gerar(n, m=3, frac_cabo=0.4, seed=seed + 3),
        ),
    ]


def carregar_instancia(referencia: str) -> tuple[Instancia, str]:
    """Aceita um caminho de arquivo JSON, ``referencia``, ou ``gerar:n[:m]``.

    Erros de dados viram mensagem de uma linha, e não traceback: quem está
    montando o arquivo de entrada precisa ler o que está errado, não a pilha de
    chamadas do Python.
    """
    caminho = Path(referencia)
    if caminho.exists():
        try:
            return dados.carregar(caminho), caminho.name
        except InstanciaInvalida as erro:
            raise SystemExit(f"Instância inválida em '{caminho}': {erro}") from None
    if referencia == "referencia":
        return dados.instancia_referencia(), "referencia"
    if referencia.startswith("gerar:"):
        partes = referencia.split(":")[1:]
        try:
            n = int(partes[0])
            m = int(partes[1]) if len(partes) > 1 else 4
            semente = int(partes[2]) if len(partes) > 2 else 0
        except (ValueError, IndexError):
            raise SystemExit(
                f"Formato inválido em '{referencia}'. Use 'gerar:n', 'gerar:n:m' "
                "ou 'gerar:n:m:seed'."
            ) from None
        return dados.gerar(n, m=m, seed=semente), referencia
    raise SystemExit(
        f"Instância '{referencia}' não encontrada. Informe um arquivo JSON "
        "existente, 'referencia', ou 'gerar:n[:m[:seed]]'."
    )


# ======================================================================
# Subcomando: resolver
# ======================================================================
def comando_resolver(args: argparse.Namespace) -> int:
    inst, nome = carregar_instancia(args.instancia)
    cfg = ConfigModelo(usar_mtz=not args.sem_mtz, penalidade_antecipacao=args.alfa)
    res = resolver(
        inst,
        cfg,
        tempo_limite=args.tempo_limite,
        solver_nome=args.solver,
        msg=args.verboso,
    )

    blocos = [relatorio.formatar_instancia(inst)]
    if res.sequencias is None:
        blocos.append(relatorio.formatar_resultado(res))
        violacoes = ["O solver não devolveu programação."]
        blocos.append(relatorio.formatar_violacoes(violacoes))
        prog = None
    else:
        # A conferência é feita fora do solver: `res.sequencias` é só a ordem
        # dos itens, e todo o resto do número é recalculado por `conferencia`.
        conf = conferir(inst, res.sequencias, res.objetivo, args.alfa)
        prog, violacoes = conf.programacao, conf.violacoes
        blocos.append(relatorio.formatar_resultado(res, conf.divergencia))
        blocos.append(relatorio.formatar_programacao(inst, prog))
        blocos.append(relatorio.formatar_violacoes(violacoes))

    texto = "\n\n".join(blocos)
    print(texto)

    if args.saida:
        destino = Path(args.saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em: {destino}")
    if args.salvar_json:
        print(f"Instância salva em: {dados.salvar(inst, args.salvar_json, nome=nome)}")
    if args.gantt and prog is not None:
        relatorio.gantt(inst, prog, caminho=args.gantt)
        print(f"Gráfico de Gantt salvo em: {args.gantt}")

    return 0 if (prog is not None and not violacoes) else 1


# ======================================================================
# Subcomando: validar
# ======================================================================
def comando_validar(args: argparse.Namespace) -> int:
    """Confronta o PLI com a enumeração exaustiva em quatro instâncias pequenas.

    É o que dá segurança antes de escalar: cada estágio isola um aspecto do
    modelo (setup, assimetria, subciclos, elegibilidade) numa instância pequena
    o bastante para a força bruta. Se o ótimo do solver não bater com o da
    enumeração, não adianta olhar a instância de 80 itens.
    """
    cfg = ConfigModelo(usar_mtz=not args.sem_mtz)
    print("=" * 88)
    print(
        f"VALIDAÇÃO INCREMENTAL (n = {args.n}, "
        f"MTZ = {'não' if args.sem_mtz else 'sim'})"
    )
    print("=" * 88)
    print(
        f"{'estágio':<10} {'o que valida':<30} {'PLI':>10} {'força bruta':>12} "
        f"{'tempo s':>8}  resultado"
    )
    print("-" * 88)

    falhas = 0
    for nome, descricao, inst in estagios(args.n, args.seed):
        res = resolver(inst, cfg, tempo_limite=args.tempo_limite)
        otimo_bruto, _ = forca_bruta(inst)

        motivos: list[str] = []
        if res.status != "Optimal":
            motivos.append(f"status={res.status}")
        if res.objetivo is None or abs(res.objetivo - otimo_bruto) > TOLERANCIA:
            motivos.append("objetivo != força bruta")
        if res.sequencias is None:
            motivos.append("sem programação")
        else:
            conf = conferir(inst, res.sequencias, res.objetivo)
            if conf.violacoes:
                motivos.append(f"{len(conf.violacoes)} violação(ões)")

        falhas += bool(motivos)
        objetivo = "-" if res.objetivo is None else f"{res.objetivo:10.2f}"
        print(
            f"{nome:<10} {descricao:<30} {objetivo:>10} {otimo_bruto:12.2f} "
            f"{res.tempo_s:8.2f}  "
            + ("PASSOU" if not motivos else "FALHOU: " + "; ".join(motivos))
        )

    print("-" * 88)
    print(
        f"{falhas} estágio(s) FALHARAM. Não escale antes de investigar."
        if falhas
        else "Todos os estágios passaram: o modelo reproduz o ótimo exato."
    )
    print("=" * 88)
    return 1 if falhas else 0


# ======================================================================
# Subcomando: experimentos
# ======================================================================
def _escrever_csv(nome: str, linhas: list[dict[str, object]]) -> Path:
    """Grava um CSV em ``resultados/``.

    Convenção das colunas de gap: **``gap_percentual`` está sempre em
    porcentagem** (80,0 = 80%), a mesma unidade mostrada na tela. Guardar fração
    no arquivo e porcentagem na tela já produziu tabela lida errado.
    """
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_RESULTADOS / nome
    with destino.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)
    return destino


def _col(valor: float | None, largura: int = 12, casas: int = 2) -> str:
    """Coluna numérica alinhada; ``None`` vira um traço na mesma largura."""
    return f"{'-' if valor is None else format(valor, f'.{casas}f'):>{largura}}"


def _linha_solver(res: Resultado, prefixo: str) -> str:
    """Linha de tabela com status, objetivo, limite inferior, gap e tempo."""
    return (f"{prefixo} {res.status:<12} {_col(res.objetivo)} "
            f"{_col(res.limite_inferior)} {_col(res.gap_percentual, 8)} "
            f"{res.tempo_s:9.2f}")


def _arredondar(valor: float | None, casas: int = 2) -> float | None:
    return None if valor is None else round(valor, casas)


def experimento_escala(tempo_limite: int, tamanhos: list[int]) -> Path:
    """Tempo, tamanho do modelo e gap por tamanho de instância."""
    print(f"\n=== ESCALA (limite de {tempo_limite} s por instância) ===")
    print(
        f"{'n':>4} {'vars':>8} {'restr':>8} {'status':<12} {'objetivo':>12} "
        f"{'lim.inf.':>12} {'gap %':>8} {'tempo s':>9}"
    )
    linhas: list[dict[str, object]] = []
    for n in tamanhos:
        inst = dados.gerar(n, seed=SEMENTES[0])
        res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=tempo_limite)
        print(_linha_solver(
            res, f"{n:>4} {res.n_variaveis:>8} {res.n_restricoes:>8}"
        ))
        linhas.append(
            {
                "n": n,
                "seed": SEMENTES[0],
                "n_variaveis": res.n_variaveis,
                "n_restricoes": res.n_restricoes,
                "status": res.status,
                "objetivo": _arredondar(res.objetivo),
                "limite_inferior": _arredondar(res.limite_inferior),
                "gap_percentual": _arredondar(res.gap_percentual),
                "tempo_s": round(res.tempo_s, 3),
            }
        )
    return _escrever_csv("escala.csv", linhas)


def experimento_mtz(tempo_limite: int, tamanhos: list[int]) -> Path:
    """MTZ ligado × desligado, com três sementes por tamanho.

    O resumo reporta **quantas execuções provaram otimalidade** e o **tempo
    médio até a prova** — e não a média dos objetivos: comparar incumbentes de
    execuções que não convergiram não permite conclusão nenhuma, porque cada uma
    parou num ponto diferente da árvore de busca.
    """
    print(f"\n=== MTZ LIGADO x DESLIGADO (limite de {tempo_limite} s) ===")
    print(
        f"{'n':>4} {'seed':>5} {'MTZ':<5} {'restr':>8} {'status':<12} "
        f"{'objetivo':>12} {'lim.inf.':>12} {'gap %':>8} {'tempo s':>9}"
    )
    linhas: list[dict[str, object]] = []
    for n in tamanhos:
        for semente in SEMENTES:
            inst = dados.gerar(n, seed=semente)
            for usar_mtz in (True, False):
                res = resolver(
                    inst, ConfigModelo(usar_mtz=usar_mtz), tempo_limite=tempo_limite
                )
                print(_linha_solver(
                    res,
                    f"{n:>4} {semente:>5} {'sim' if usar_mtz else 'não':<5} "
                    f"{res.n_restricoes:>8}",
                ))
                linhas.append(
                    {
                        "n": n,
                        "seed": semente,
                        "usar_mtz": usar_mtz,
                        "n_variaveis": res.n_variaveis,
                        "n_restricoes": res.n_restricoes,
                        "status": res.status,
                        "otimo_provado": res.otimo_provado,
                        "objetivo": _arredondar(res.objetivo),
                        "limite_inferior": _arredondar(res.limite_inferior),
                        "gap_percentual": _arredondar(res.gap_percentual),
                        "tempo_s": round(res.tempo_s, 3),
                    }
                )

    print("\n--- resumo: prova de otimalidade (não média de objetivos) ---")
    print(f"{'MTZ':<5} {'provou ótimo':>14} {'tempo médio até a prova':>26}")
    for usar_mtz in (True, False):
        provadas = [
            linha
            for linha in linhas
            if linha["usar_mtz"] is usar_mtz and linha["otimo_provado"]
        ]
        total = sum(1 for linha in linhas if linha["usar_mtz"] is usar_mtz)
        medio = (
            sum(float(linha["tempo_s"]) for linha in provadas) / len(provadas)
            if provadas
            else None
        )
        print(
            f"{'sim' if usar_mtz else 'não':<5} {f'{len(provadas)}/{total}':>14} "
            f"{'-' if medio is None else format(medio, '23.2f') + ' s':>26}"
        )
    return _escrever_csv("mtz.csv", linhas)


def experimento_edd(tempo_limite: int, tamanhos: list[int]) -> Path:
    """Modelo exato × EDD, com três sementes por tamanho.

    Só produz a coluna de comparação do relatório. O EDD **não** é o método de
    solução do trabalho — ver o aviso em :func:`conferencia.edd`.
    """
    print(f"\n=== MODELO EXATO x EDD (comparação, limite de {tempo_limite} s) ===")
    print(
        f"{'n':>4} {'seed':>5} {'status':<12} {'PLI':>12} {'EDD':>12} "
        f"{'ganho %':>9}"
    )
    linhas: list[dict[str, object]] = []
    for n in tamanhos:
        for semente in SEMENTES:
            inst = dados.gerar(n, seed=semente)
            res = resolver(
                inst, ConfigModelo(usar_mtz=True), tempo_limite=tempo_limite
            )
            objetivo_edd = edd(inst).objetivo
            ganho = (
                None
                if res.objetivo is None or objetivo_edd == 0
                else 100 * (objetivo_edd - res.objetivo) / objetivo_edd
            )
            print(
                f"{n:>4} {semente:>5} {res.status:<12} {_col(res.objetivo)} "
                f"{objetivo_edd:>12.2f} {_col(ganho, 9, 1)}"
            )
            registro: dict[str, object] = {
                "n": n,
                "seed": semente,
                "status_pli": res.status,
                "otimo_provado": res.otimo_provado,
                "objetivo_pli": _arredondar(res.objetivo),
                "gap_percentual": _arredondar(res.gap_percentual),
                "tempo_pli_s": round(res.tempo_s, 3),
                "objetivo_edd": _arredondar(objetivo_edd),
                "ganho_percentual_pli": _arredondar(ganho),
            }
            if res.sequencias is not None:
                prog = conferir(inst, res.sequencias, res.objetivo).programacao
                indicadores = relatorio.metricas(prog, inst)
                registro["n_atrasados_pli"] = indicadores["n_atrasados"]
                registro["makespan_pli"] = _arredondar(indicadores["makespan"])
            linhas.append(registro)
    return _escrever_csv("edd.csv", linhas)


def comando_experimentos(args: argparse.Namespace) -> int:
    funcoes = {
        "escala": experimento_escala,
        "mtz": experimento_mtz,
        "edd": experimento_edd,
    }
    escolhidos = list(funcoes) if args.experimento == "todos" else [args.experimento]
    for nome in escolhidos:
        destino = funcoes[nome](args.tempo_limite, args.tamanhos)
        print(f"\nCSV salvo em: {destino}")
    return 0


# ======================================================================
# CLI
# ======================================================================
def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Programação da produção de correias por Programação Linear Inteira "
            "Mista (PLI)."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_resolver = sub.add_parser(
        "resolver", help="resolve uma instância e confere a solução"
    )
    p_resolver.add_argument(
        "--instancia",
        default="referencia",
        help="arquivo JSON, 'referencia' ou 'gerar:n[:m[:seed]]'",
    )
    p_resolver.add_argument(
        "--tempo-limite", type=int, default=TEMPO_LIMITE_PADRAO,
        help="limite de tempo do solver, em segundos",
    )
    p_resolver.add_argument(
        "--sem-mtz", action="store_true",
        help="desliga as restrições MTZ (6), que são redundantes",
    )
    p_resolver.add_argument(
        "--alfa", type=float, default=0.0,
        help="penalidade de antecipação (estocagem limitada); 0 desliga",
    )
    p_resolver.add_argument("--solver", default="CBC", help="CBC ou HiGHS")
    p_resolver.add_argument("--gantt", metavar="ARQUIVO", help="salva o Gantt aqui")
    p_resolver.add_argument(
        "--saida", metavar="ARQUIVO", help="salva o relatório textual aqui"
    )
    p_resolver.add_argument(
        "--salvar-json", metavar="ARQUIVO", help="grava a instância usada em JSON"
    )
    p_resolver.add_argument(
        "--verboso", action="store_true", help="mostra o log do solver"
    )
    p_resolver.set_defaults(funcao=comando_resolver)

    p_validar = sub.add_parser(
        "validar", help="valida o modelo contra a enumeração exaustiva"
    )
    p_validar.add_argument(
        "--n", type=int, default=5, help="itens por estágio (máximo 8)"
    )
    p_validar.add_argument("--seed", type=int, default=11, help="semente base")
    p_validar.add_argument(
        "--tempo-limite", type=int, default=TEMPO_LIMITE_PADRAO,
        help="limite do solver, em segundos",
    )
    p_validar.add_argument("--sem-mtz", action="store_true", help="desliga o MTZ")
    p_validar.set_defaults(funcao=comando_validar)

    p_exp = sub.add_parser("experimentos", help="bateria de experimentos do relatório")
    p_exp.add_argument(
        "--experimento", choices=["escala", "mtz", "edd", "todos"], default="todos"
    )
    p_exp.add_argument(
        "--tempo-limite", type=int, default=TEMPO_LIMITE_PADRAO,
        help="limite por resolução, em segundos (o mesmo nos três experimentos)",
    )
    p_exp.add_argument("--tamanhos", type=int, nargs="+", default=TAMANHOS)
    p_exp.set_defaults(funcao=comando_experimentos)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    relatorio.configurar_saida()
    return int(args.funcao(args))


if __name__ == "__main__":
    raise SystemExit(main())
