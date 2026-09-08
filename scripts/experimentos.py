"""Bateria de experimentos para o relatório.

Três experimentos, todos salvando CSV em ``resultados/``:

``escala``
    tempo de resolução, status e gap por tamanho de instância
    (n = 6, 10, 15, 20, 30, 50, 80). Mostra onde o modelo exato deixa de
    fechar o gap no tempo disponível.
``mtz``
    o mesmo conjunto de instâncias com e sem as restrições (6), para medir o
    efeito das restrições redundantes sobre o limite inferior e o tempo.
``baselines``
    regras de despacho contra o modelo exato — **apenas comparação**; ver o
    aviso em :mod:`rubbertech.baselines`.

Uso::

    python scripts/experimentos.py --experimento escala --tempo-limite 60
    python scripts/experimentos.py --experimento todos
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rubbertech import baselines, relatorio  # noqa: E402
from rubbertech.dominio import Instancia  # noqa: E402
from rubbertech.instancias import estagio_6_completo  # noqa: E402
from rubbertech.modelo import ConfigModelo  # noqa: E402
from rubbertech.solucao import metricas  # noqa: E402
from rubbertech.solver import resolver  # noqa: E402

#: Tamanhos da bateria de escala.
TAMANHOS = [6, 10, 15, 20, 30, 50, 80]
#: Diretório de saída dos CSVs.
PASTA_RESULTADOS = Path(__file__).resolve().parents[1] / "resultados"


def instancia_de_tamanho(n: int, seed: int = 6) -> Instancia:
    """Instância com a estrutura da carteira real, no tamanho pedido."""
    return estagio_6_completo(seed=seed, n=n)


def _escrever_csv(nome: str, linhas: list[dict[str, object]]) -> Path:
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_RESULTADOS / nome
    with destino.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)
    return destino


def experimento_escala(tempo_limite: int, tamanhos: list[int]) -> Path:
    """Tempo e gap por tamanho de instância."""
    linhas: list[dict[str, object]] = []
    print(f"\n=== ESCALA (limite de {tempo_limite} s por instância) ===")
    cabecalho = (
        f"{'n':>4} {'vars':>8} {'restr':>8} {'status':<12} {'objetivo':>12} "
        f"{'lim.inf.':>12} {'gap %':>8} {'tempo s':>9}"
    )
    print(cabecalho)
    for n in tamanhos:
        inst = instancia_de_tamanho(n)
        res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=tempo_limite)
        print(
            f"{n:>4} {res.n_variaveis:>8} {res.n_restricoes:>8} {res.status:<12} "
            f"{'-' if res.objetivo is None else format(res.objetivo, '12.2f')} "
            f"{'-' if res.limite_inferior is None else format(res.limite_inferior, '12.2f')} "
            f"{'-' if res.gap is None else format(100 * res.gap, '8.2f')} "
            f"{res.tempo_s:9.2f}"
        )
        linhas.append(
            {
                "n": n,
                "n_variaveis": res.n_variaveis,
                "n_restricoes": res.n_restricoes,
                "status": res.status,
                "objetivo": res.objetivo,
                "limite_inferior": res.limite_inferior,
                "gap": res.gap,
                "tempo_s": round(res.tempo_s, 3),
            }
        )
    return _escrever_csv("escala.csv", linhas)


def experimento_mtz(tempo_limite: int, tamanhos: list[int]) -> Path:
    """MTZ ligado × desligado: efeito das restrições redundantes."""
    linhas: list[dict[str, object]] = []
    print(f"\n=== MTZ LIGADO x DESLIGADO (limite de {tempo_limite} s) ===")
    print(
        f"{'n':>4} {'MTZ':<5} {'restr':>8} {'status':<12} {'objetivo':>12} "
        f"{'lim.inf.':>12} {'gap %':>8} {'tempo s':>9}"
    )
    for n in tamanhos:
        inst = instancia_de_tamanho(n)
        for usar_mtz in (True, False):
            res = resolver(
                inst, ConfigModelo(usar_mtz=usar_mtz), tempo_limite=tempo_limite
            )
            print(
                f"{n:>4} {'sim' if usar_mtz else 'não':<5} {res.n_restricoes:>8} "
                f"{res.status:<12} "
                f"{'-' if res.objetivo is None else format(res.objetivo, '12.2f')} "
                f"{'-' if res.limite_inferior is None else format(res.limite_inferior, '12.2f')} "
                f"{'-' if res.gap is None else format(100 * res.gap, '8.2f')} "
                f"{res.tempo_s:9.2f}"
            )
            linhas.append(
                {
                    "n": n,
                    "usar_mtz": usar_mtz,
                    "n_variaveis": res.n_variaveis,
                    "n_restricoes": res.n_restricoes,
                    "status": res.status,
                    "objetivo": res.objetivo,
                    "limite_inferior": res.limite_inferior,
                    "gap": res.gap,
                    "tempo_s": round(res.tempo_s, 3),
                }
            )
    return _escrever_csv("mtz.csv", linhas)


def experimento_baselines(tempo_limite: int, tamanhos: list[int]) -> Path:
    """Regras de despacho contra o modelo exato.

    Só produz a coluna de comparação do relatório. As regras não são o método de
    solução do trabalho — ver o aviso no topo de :mod:`rubbertech.baselines`.
    """
    linhas: list[dict[str, object]] = []
    print(f"\n=== MODELO EXATO x REGRAS DE DESPACHO (comparação) ===")
    print(
        f"{'n':>4} {'PLI':>12} {'status':<12} "
        + " ".join(f"{nome:>10}" for nome in baselines.REGRAS)
        + f" {'melhor regra':>13} {'ganho %':>9}"
    )
    for n in tamanhos:
        inst = instancia_de_tamanho(n)
        res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=tempo_limite)
        valores = {
            nome: regra(inst).objetivo for nome, regra in baselines.REGRAS.items()
        }
        melhor_regra = min(valores, key=lambda nome: valores[nome])
        melhor_valor = valores[melhor_regra]
        ganho = (
            None
            if res.objetivo is None or melhor_valor == 0
            else 100 * (melhor_valor - res.objetivo) / melhor_valor
        )
        print(
            f"{n:>4} "
            f"{'-' if res.objetivo is None else format(res.objetivo, '12.2f')} "
            f"{res.status:<12} "
            + " ".join(f"{valores[nome]:>10.2f}" for nome in baselines.REGRAS)
            + f" {melhor_regra:>13} "
            + ("-" if ganho is None else f"{ganho:>9.1f}")
        )
        registro: dict[str, object] = {
            "n": n,
            "status_pli": res.status,
            "objetivo_pli": res.objetivo,
            "tempo_pli_s": round(res.tempo_s, 3),
        }
        for nome, valor in valores.items():
            registro[f"objetivo_{nome}"] = valor
        registro["melhor_regra"] = melhor_regra
        registro["ganho_percentual_pli"] = None if ganho is None else round(ganho, 2)
        if res.programacao is not None:
            indicadores = metricas(res.programacao, inst)
            registro["n_atrasados_pli"] = indicadores["n_atrasados"]
            registro["makespan_pli"] = indicadores["makespan"]
        linhas.append(registro)
    return _escrever_csv("baselines.csv", linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--experimento",
        choices=["escala", "mtz", "baselines", "todos"],
        default="todos",
    )
    parser.add_argument(
        "--tempo-limite", type=int, default=60, help="limite por resolução, em s"
    )
    parser.add_argument(
        "--tamanhos",
        type=int,
        nargs="+",
        default=TAMANHOS,
        help="tamanhos de instância a testar",
    )
    args = parser.parse_args(argv)
    relatorio.configurar_saida()

    escolhidos = (
        ["escala", "mtz", "baselines"]
        if args.experimento == "todos"
        else [args.experimento]
    )
    funcoes = {
        "escala": experimento_escala,
        "mtz": experimento_mtz,
        "baselines": experimento_baselines,
    }
    for nome in escolhidos:
        destino = funcoes[nome](args.tempo_limite, args.tamanhos)
        print(f"\nCSV salvo em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
