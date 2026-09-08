"""CLI principal: resolve uma instância por PLI e imprime o resultado.

Uso típico::

    python scripts/resolver.py --instancia referencia
    python scripts/resolver.py --instancia data/instancias/minha.json --gantt g.png

A instância pode vir de um arquivo JSON ou de um dos geradores paramétricos
(``referencia``, ``estagio_1`` … ``estagio_6``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite rodar o script sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rubbertech import io_dados, relatorio  # noqa: E402
from rubbertech.dominio import Instancia, InstanciaInvalida  # noqa: E402
from rubbertech.instancias import GERADORES  # noqa: E402
from rubbertech.modelo import ConfigModelo  # noqa: E402
from rubbertech.solver import resolver as resolver_instancia  # noqa: E402
from rubbertech.validacao import verificar  # noqa: E402


def carregar_instancia(referencia: str) -> tuple[Instancia, str]:
    """Aceita tanto um caminho de arquivo JSON quanto o nome de um gerador.

    Erros de dados viram mensagem de uma linha, e não traceback: quem está
    montando o arquivo de entrada precisa ler o que está errado, não a pilha de
    chamadas do Python.
    """
    caminho = Path(referencia)
    if caminho.exists():
        try:
            return io_dados.carregar(caminho), caminho.name
        except InstanciaInvalida as erro:
            raise SystemExit(f"Instância inválida em '{caminho}': {erro}") from None
    if referencia in GERADORES:
        return GERADORES[referencia](), referencia
    raise SystemExit(
        f"Instância '{referencia}' não encontrada. Informe um arquivo JSON "
        f"existente ou um destes geradores: {', '.join(GERADORES)}."
    )


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve a programação da produção por Programação Linear Inteira "
            "Mista (PLI)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--instancia",
        default="referencia",
        help="arquivo JSON ou nome de gerador (%s)" % ", ".join(GERADORES),
    )
    parser.add_argument(
        "--tempo-limite",
        type=int,
        default=300,
        help="limite de tempo do solver, em segundos",
    )
    parser.add_argument(
        "--sem-mtz",
        action="store_true",
        help="desliga as restrições MTZ (6), que são redundantes",
    )
    parser.add_argument(
        "--alfa",
        type=float,
        default=0.0,
        help="penalidade de antecipação (estocagem limitada); 0 desliga",
    )
    parser.add_argument(
        "--solver", default="CBC", help="solver a usar: CBC ou HiGHS"
    )
    parser.add_argument(
        "--gantt", metavar="ARQUIVO", help="salva o gráfico de Gantt neste caminho"
    )
    parser.add_argument(
        "--saida", metavar="ARQUIVO", help="salva o relatório textual neste caminho"
    )
    parser.add_argument(
        "--salvar-json",
        metavar="ARQUIVO",
        help="grava a instância usada em JSON (útil para editar os dados depois)",
    )
    parser.add_argument(
        "--verboso", action="store_true", help="mostra o log do solver"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    relatorio.configurar_saida()

    inst, nome = carregar_instancia(args.instancia)
    cfg = ConfigModelo(
        usar_mtz=not args.sem_mtz, penalidade_antecipacao=args.alfa
    )
    resultado = resolver_instancia(
        inst,
        cfg,
        tempo_limite=args.tempo_limite,
        solver_nome=args.solver,
        msg=args.verboso,
    )

    blocos = [
        relatorio.formatar_instancia(inst),
        relatorio.formatar_resultado(resultado),
    ]
    if resultado.programacao is not None:
        blocos.append(relatorio.formatar_programacao(inst, resultado.programacao))
        violacoes = verificar(inst, resultado.programacao, args.alfa)
        blocos.append(relatorio.formatar_violacoes(violacoes))
    else:
        violacoes = ["O solver não devolveu programação."]

    texto = "\n\n".join(blocos)
    print(texto)

    if args.saida:
        destino = Path(args.saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"\nRelatório salvo em: {destino}")

    if args.salvar_json:
        caminho = io_dados.salvar(inst, args.salvar_json, nome=nome)
        print(f"Instância salva em: {caminho}")

    if args.gantt and resultado.programacao is not None:
        from rubbertech.visual import gantt

        gantt(inst, resultado.programacao, caminho=args.gantt)
        print(f"Gráfico de Gantt salvo em: {args.gantt}")

    return 0 if (resultado.programacao is not None and not violacoes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
