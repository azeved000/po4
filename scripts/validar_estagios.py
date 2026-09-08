"""Validação incremental: estágios 1 a 4 contra a enumeração exaustiva.

É o script que dá segurança antes de escalar. Cada estágio isola um aspecto do
modelo (setup, assimetria, subciclos, elegibilidade) em uma instância pequena o
bastante para ser resolvida por força bruta. Se o ótimo do solver não bater com
o da enumeração, não adianta olhar a instância de 80 itens.

Uso::

    python scripts/validar_estagios.py
    python scripts/validar_estagios.py --n 5 --sem-mtz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rubbertech import instancias, relatorio  # noqa: E402
from rubbertech.dominio import Instancia  # noqa: E402
from rubbertech.modelo import ConfigModelo  # noqa: E402
from rubbertech.solver import resolver  # noqa: E402
from rubbertech.validacao import forca_bruta, verificar  # noqa: E402

#: Tolerância na comparação entre solver e enumeração (erro numérico do CBC).
TOLERANCIA = 1e-4


def montar_estagios(n: int, seed: int) -> list[tuple[str, str, Instancia]]:
    """Os quatro estágios pequenos, com o que cada um se propõe a validar."""
    return [
        (
            "estágio 1",
            "uma linha, setup zero",
            instancias.estagio_1_maquina_unica(n=n, seed=seed),
        ),
        (
            "estágio 2",
            "uma linha, setup assimétrico",
            instancias.estagio_2_setup(n=n, seed=seed + 1),
        ),
        (
            "estágio 3",
            "armadilha de subciclo",
            instancias.estagio_3_subciclos(n=n, seed=seed + 2),
        ),
        (
            "estágio 4",
            "elegibilidade restrita",
            instancias.estagio_4_elegibilidade(
                n=n + 1, m=3, frac_cabo=0.34, seed=seed + 3
            ),
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--n", type=int, default=5, help="itens por estágio (máximo 8)"
    )
    parser.add_argument("--seed", type=int, default=11, help="semente base")
    parser.add_argument(
        "--tempo-limite", type=int, default=120, help="limite do solver, em s"
    )
    parser.add_argument("--sem-mtz", action="store_true", help="desliga o MTZ")
    args = parser.parse_args(argv)
    relatorio.configurar_saida()

    cfg = ConfigModelo(usar_mtz=not args.sem_mtz)
    cabecalho = (
        f"{'estágio':<10} {'o que valida':<30} {'PLI':>10} {'força bruta':>12} "
        f"{'tempo s':>8}  resultado"
    )
    print("=" * 88)
    print(f"VALIDAÇÃO INCREMENTAL (n = {args.n}, MTZ = {'não' if args.sem_mtz else 'sim'})")
    print("=" * 88)
    print(cabecalho)
    print("-" * 88)

    falhas = 0
    for nome, descricao, inst in montar_estagios(args.n, args.seed):
        res = resolver(inst, cfg, tempo_limite=args.tempo_limite)
        otimo_bruto, _ = forca_bruta(inst)

        motivos: list[str] = []
        if res.status != "Optimal":
            motivos.append(f"status={res.status}")
        if res.objetivo is None or abs(res.objetivo - otimo_bruto) > TOLERANCIA:
            motivos.append("objetivo != força bruta")
        if res.programacao is not None:
            violacoes = verificar(inst, res.programacao)
            if violacoes:
                motivos.append(f"{len(violacoes)} violação(ões)")
        else:
            motivos.append("sem programação")

        situacao = "PASSOU" if not motivos else "FALHOU: " + "; ".join(motivos)
        falhas += bool(motivos)
        objetivo = "-" if res.objetivo is None else f"{res.objetivo:10.2f}"
        print(
            f"{nome:<10} {descricao:<30} {objetivo:>10} {otimo_bruto:12.2f} "
            f"{res.tempo_s:8.2f}  {situacao}"
        )

    print("-" * 88)
    if falhas:
        print(f"{falhas} estágio(s) FALHARAM. Não escale antes de investigar.")
    else:
        print("Todos os estágios passaram: o modelo reproduz o ótimo exato.")
    print("=" * 88)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
