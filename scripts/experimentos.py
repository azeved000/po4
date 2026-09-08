"""Bateria de experimentos para o relatório.

Três experimentos, todos salvando CSV em ``resultados/``:

``escala``
    tempo de resolução, status e gap por tamanho de instância
    (n = 6, 10, 15, 20, 30, 50, 80). Mostra onde o modelo exato deixa de
    fechar o gap no tempo disponível.
``mtz``
    o mesmo modelo com e sem as restrições (6), em **várias sementes por
    tamanho**, para medir o efeito das restrições redundantes sobre a prova de
    otimalidade. Uma execução por tamanho não distingue efeito de formulação de
    ruído na ordem de exploração da árvore — por isso a repetição.
``baselines``
    regras de despacho contra o modelo exato — **apenas comparação**; ver o
    aviso em :mod:`rubbertech.baselines`.

Convenção de unidades: a coluna de gap dos CSVs se chama ``gap_percentual`` e é
gravada **já em porcentagem** (``0`` = ótimo provado, ``100`` = incumbente vale
o dobro do limite inferior), igual ao que aparece na tela e no README. Vazio
significa gap indefinido (limite inferior nulo), não gap zero.

Uso::

    python scripts/experimentos.py --experimento escala --tempo-limite 120
    python scripts/experimentos.py --experimento mtz --tempo-limite 120
    python scripts/experimentos.py --experimento todos
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rubbertech import baselines, relatorio  # noqa: E402
from rubbertech.dominio import Instancia  # noqa: E402
from rubbertech.instancias import estagio_6_completo  # noqa: E402
from rubbertech.modelo import ConfigModelo  # noqa: E402
from rubbertech.solucao import metricas  # noqa: E402
from rubbertech.solver import resolver  # noqa: E402

#: Tamanhos da bateria de escala.
TAMANHOS = [6, 10, 15, 20, 30, 50, 80]
#: Tamanhos da comparação MTZ ligado × desligado. Faixa em que ainda há chance
#: de prova de otimalidade dentro do orçamento — é isso que a comparação mede.
TAMANHOS_MTZ = [6, 8, 10, 12]
#: Tamanhos da comparação contra as regras de despacho.
TAMANHOS_BASELINES = [6, 8, 10, 15, 20]
#: Sementes fixas usadas em todos os experimentos com repetição. Ficam
#: registradas no CSV para que cada linha seja reproduzível isoladamente.
SEMENTES = [6, 7, 8]
#: Diretório de saída dos CSVs.
PASTA_RESULTADOS = Path(__file__).resolve().parents[1] / "resultados"


def _col(valor: float | None, largura: int, casas: int = 2) -> str:
    """Formata um número em coluna de largura fixa; ``None`` vira traço alinhado."""
    if valor is None:
        return "-".rjust(largura)
    return format(valor, f"{largura}.{casas}f")


def _gap_percentual(gap: float | None) -> float | None:
    """Converte o gap fracionário do solver para a porcentagem gravada no CSV."""
    return None if gap is None else round(100 * gap, 2)


def instancia_de_tamanho(n: int, seed: int = 6) -> Instancia:
    """Instância com a estrutura da carteira real, no tamanho e semente pedidos."""
    return estagio_6_completo(seed=seed, n=n)


def _escrever_csv(nome: str, linhas: list[dict[str, object]]) -> Path:
    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_RESULTADOS / nome
    with destino.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)
    return destino


def experimento_escala(
    tempo_limite: int, tamanhos: list[int], sementes: list[int]
) -> Path:
    """Tempo e gap por tamanho de instância.

    Roda com a primeira semente da lista: este experimento mede o crescimento do
    modelo e do esforço com ``n``, não a variação entre instâncias do mesmo
    tamanho.
    """
    seed = sementes[0]
    linhas: list[dict[str, object]] = []
    print(f"\n=== ESCALA (limite de {tempo_limite} s por instância, semente {seed}) ===")
    cabecalho = (
        f"{'n':>4} {'vars':>8} {'restr':>8} {'status':<12} {'objetivo':>12} "
        f"{'lim.inf.':>12} {'gap %':>8} {'tempo s':>9}"
    )
    print(cabecalho)
    for n in tamanhos:
        inst = instancia_de_tamanho(n, seed=seed)
        res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=tempo_limite)
        print(
            f"{n:>4} {res.n_variaveis:>8} {res.n_restricoes:>8} {res.status:<12} "
            f"{_col(res.objetivo, 12)} "
            f"{_col(res.limite_inferior, 12)} "
            f"{_col(_gap_percentual(res.gap), 8)} "
            f"{res.tempo_s:9.2f}"
        )
        linhas.append(
            {
                "n": n,
                "semente": seed,
                "n_variaveis": res.n_variaveis,
                "n_restricoes": res.n_restricoes,
                "status": res.status,
                "objetivo": res.objetivo,
                "limite_inferior": res.limite_inferior,
                "gap_percentual": _gap_percentual(res.gap),
                "tempo_s": round(res.tempo_s, 3),
                "mensagem_solver": res.mensagem,
            }
        )
    return _escrever_csv("escala.csv", linhas)


def experimento_mtz(
    tempo_limite: int, tamanhos: list[int], sementes: list[int]
) -> Path:
    """MTZ ligado × desligado, com repetição por semente.

    O que a comparação mede é **prova de otimalidade**: quantas execuções cada
    configuração fechou e em quanto tempo. Comparar incumbentes de execuções que
    pararam no limite de tempo não permite conclusão — dois valores com o gap
    aberto medem a heurística interna do solver dentro do orçamento, não a
    qualidade da formulação.
    """
    linhas: list[dict[str, object]] = []
    print(
        f"\n=== MTZ LIGADO x DESLIGADO "
        f"(limite de {tempo_limite} s, sementes {sementes}) ==="
    )
    print(
        f"{'n':>4} {'seed':>5} {'MTZ':<5} {'vars':>7} {'restr':>8} {'status':<12} "
        f"{'objetivo':>12} {'lim.inf.':>12} {'gap %':>9} {'tempo s':>9}"
    )
    for n in tamanhos:
        for seed in sementes:
            inst = instancia_de_tamanho(n, seed=seed)
            for usar_mtz in (True, False):
                res = resolver(
                    inst, ConfigModelo(usar_mtz=usar_mtz), tempo_limite=tempo_limite
                )
                print(
                    f"{n:>4} {seed:>5} {'sim' if usar_mtz else 'não':<5} "
                    f"{res.n_variaveis:>7} {res.n_restricoes:>8} {res.status:<12} "
                    f"{_col(res.objetivo, 12)} "
                    f"{_col(res.limite_inferior, 12)} "
                    f"{_col(_gap_percentual(res.gap), 9)} "
                    f"{res.tempo_s:9.2f}"
                )
                linhas.append(
                    {
                        "n": n,
                        "semente": seed,
                        "usar_mtz": usar_mtz,
                        "n_variaveis": res.n_variaveis,
                        "n_restricoes": res.n_restricoes,
                        "status": res.status,
                        "objetivo": res.objetivo,
                        "limite_inferior": res.limite_inferior,
                        "gap_percentual": _gap_percentual(res.gap),
                        "tempo_s": round(res.tempo_s, 3),
                        "otimo_provado": res.otimo_provado,
                        "mensagem_solver": res.mensagem,
                    }
                )
    destino = _escrever_csv("mtz.csv", linhas)
    _resumo_mtz(linhas, tamanhos, sementes)
    return destino


def _resumo_mtz(
    linhas: list[dict[str, object]], tamanhos: list[int], sementes: list[int]
) -> Path:
    """Resumo por tamanho: quantas execuções provaram o ótimo e em quanto tempo.

    É a única leitura que a metodologia sustenta. O tempo médio é calculado
    **só** sobre as execuções que provaram otimalidade; onde nenhuma provou, não
    há tempo a reportar e a coluna fica vazia.
    """
    resumo: list[dict[str, object]] = []
    print(f"\n--- RESUMO POR TAMANHO ({len(sementes)} sementes por configuração) ---")
    print(
        f"{'n':>4} {'MTZ':<5} {'provou ótimo':>13} {'tempo médio até a prova':>25} "
        f"{'obj. ótimo (quando provado)':>29}"
    )
    for n in tamanhos:
        for usar_mtz in (True, False):
            grupo = [
                linha
                for linha in linhas
                if linha["n"] == n and linha["usar_mtz"] is usar_mtz
            ]
            provados = [linha for linha in grupo if linha["otimo_provado"]]
            tempos = [float(linha["tempo_s"]) for linha in provados]
            otimos = sorted({round(float(linha["objetivo"]), 2) for linha in provados})
            tempo_medio = mean(tempos) if tempos else None
            print(
                f"{n:>4} {'sim' if usar_mtz else 'não':<5} "
                f"{f'{len(provados)}/{len(grupo)}':>13} "
                f"{(_col(tempo_medio, 8) + ' s') if tempos else '-'.rjust(25):>25} "
                f"{(', '.join(f'{v:.2f}' for v in otimos) or '-'):>29}"
            )
            resumo.append(
                {
                    "n": n,
                    "usar_mtz": usar_mtz,
                    "execucoes": len(grupo),
                    "provaram_otimo": len(provados),
                    "tempo_medio_ate_prova_s": (
                        None if tempo_medio is None else round(tempo_medio, 3)
                    ),
                    "objetivos_otimos_provados": ";".join(f"{v:.2f}" for v in otimos),
                }
            )
    print(
        "\nLeitura: a comparação válida é a coluna 'provou ótimo' e o tempo até a\n"
        "prova. Onde nenhuma das duas configurações provou otimalidade, comparar\n"
        "os incumbentes NÃO permite concluir nada sobre a formulação — mede-se a\n"
        "heurística do CBC dentro do orçamento de tempo, e não o efeito do MTZ."
    )
    return _escrever_csv("mtz_resumo.csv", resumo)


def experimento_baselines(
    tempo_limite: int, tamanhos: list[int], sementes: list[int]
) -> Path:
    """Regras de despacho contra o modelo exato.

    Só produz a coluna de comparação do relatório. As regras não são o método de
    solução do trabalho — ver o aviso no topo de :mod:`rubbertech.baselines`.

    A comparação só é uma afirmação sobre **qualidade da solução** quando o PLI
    provou otimalidade. Quando ele parou no limite de tempo, o que se compara é
    um incumbente qualquer contra a regra — e esse incumbente pode ser pior que
    a regra, o que é registrado explicitamente e não contradiz a correção do
    modelo: o ótimo verdadeiro é necessariamente ≤ ao valor de qualquer regra.
    """
    linhas: list[dict[str, object]] = []
    print(
        f"\n=== MODELO EXATO x REGRAS DE DESPACHO "
        f"(limite de {tempo_limite} s, sementes {sementes}) ==="
    )
    print(
        f"{'n':>4} {'seed':>5} {'PLI':>12} {'status':<12} "
        + " ".join(f"{nome:>10}" for nome in baselines.REGRAS)
        + f" {'melhor regra':>13} {'ganho %':>9} {'tempo s':>9}  comparação"
    )
    for n in tamanhos:
        for seed in sementes:
            inst = instancia_de_tamanho(n, seed=seed)
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
            pli_pior = res.objetivo is not None and res.objetivo > melhor_valor
            natureza = (
                "ótimo provado"
                if res.otimo_provado
                else "incumbente no limite de tempo"
            )
            print(
                f"{n:>4} {seed:>5} "
                f"{_col(res.objetivo, 12)} "
                f"{res.status:<12} "
                + " ".join(f"{valores[nome]:>10.2f}" for nome in baselines.REGRAS)
                + f" {melhor_regra:>13} "
                + ("-".rjust(9) if ganho is None else f"{ganho:>9.1f}")
                + f" {res.tempo_s:9.2f}  {natureza}"
                + ("  <- PLI PIOR QUE A REGRA" if pli_pior else "")
            )
            registro: dict[str, object] = {
                "n": n,
                "semente": seed,
                "status_pli": res.status,
                "otimo_provado": res.otimo_provado,
                "natureza_comparacao": natureza,
                "objetivo_pli": res.objetivo,
                "limite_inferior_pli": res.limite_inferior,
                "gap_percentual": _gap_percentual(res.gap),
                "tempo_pli_s": round(res.tempo_s, 3),
            }
            for nome, valor in valores.items():
                registro[f"objetivo_{nome}"] = valor
            registro["melhor_regra"] = melhor_regra
            registro["objetivo_melhor_regra"] = melhor_valor
            registro["ganho_percentual_pli"] = None if ganho is None else round(ganho, 2)
            registro["pli_pior_que_regra"] = pli_pior
            if res.programacao is not None:
                indicadores = metricas(res.programacao, inst)
                registro["n_atrasados_pli"] = indicadores["n_atrasados"]
                registro["makespan_pli"] = indicadores["makespan"]
            linhas.append(registro)
    destino = _escrever_csv("baselines.csv", linhas)
    _resumo_baselines(linhas, tamanhos)
    return destino


def _resumo_baselines(linhas: list[dict[str, object]], tamanhos: list[int]) -> Path:
    """Resumo por tamanho, separando ótimo provado de incumbente."""
    resumo: list[dict[str, object]] = []
    print("\n--- RESUMO POR TAMANHO ---")
    print(
        f"{'n':>4} {'provou ótimo':>13} {'ganho médio (ótimo provado)':>29} "
        f"{'exec. com PLI pior que a regra':>32}"
    )
    for n in tamanhos:
        grupo = [linha for linha in linhas if linha["n"] == n]
        provados = [linha for linha in grupo if linha["otimo_provado"]]
        ganhos = [
            float(linha["ganho_percentual_pli"])
            for linha in provados
            if linha["ganho_percentual_pli"] is not None
        ]
        piores = [linha for linha in grupo if linha["pli_pior_que_regra"]]
        ganho_medio = mean(ganhos) if ganhos else None
        print(
            f"{n:>4} {f'{len(provados)}/{len(grupo)}':>13} "
            f"{(f'{ganho_medio:.2f} %' if ganho_medio is not None else '-'):>29} "
            f"{f'{len(piores)}/{len(grupo)}':>32}"
        )
        resumo.append(
            {
                "n": n,
                "execucoes": len(grupo),
                "provaram_otimo": len(provados),
                "ganho_medio_percentual_otimo_provado": (
                    None if ganho_medio is None else round(ganho_medio, 2)
                ),
                "execucoes_pli_pior_que_regra": len(piores),
            }
        )
    print(
        "\nLeitura: 'ganho médio' só é calculado sobre execuções com otimalidade\n"
        "provada — é a única comparação que afirma algo sobre a qualidade da\n"
        "regra. Onde o PLI parou no limite de tempo, o valor dele é apenas um\n"
        "limitante superior e pode ficar acima do valor de uma regra de despacho."
    )
    return _escrever_csv("baselines_resumo.csv", resumo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--experimento",
        choices=["escala", "mtz", "baselines", "todos"],
        default="todos",
    )
    parser.add_argument(
        "--tempo-limite", type=int, default=120, help="limite por resolução, em s"
    )
    parser.add_argument(
        "--tamanhos",
        type=int,
        nargs="+",
        default=None,
        help="tamanhos de instância a testar (o padrão depende do experimento)",
    )
    parser.add_argument(
        "--sementes",
        type=int,
        nargs="+",
        default=SEMENTES,
        help="sementes dos geradores; repetição por tamanho nos experimentos "
        "mtz e baselines",
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
    padroes = {
        "escala": TAMANHOS,
        "mtz": TAMANHOS_MTZ,
        "baselines": TAMANHOS_BASELINES,
    }
    for nome in escolhidos:
        tamanhos = args.tamanhos if args.tamanhos is not None else padroes[nome]
        destino = funcoes[nome](args.tempo_limite, tamanhos, args.sementes)
        print(f"\nCSV salvo em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
