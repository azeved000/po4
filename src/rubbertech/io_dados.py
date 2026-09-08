"""Persistência de instâncias em JSON.

O formato foi escolhido para ser escrito **à mão** por quem tem os dados da
fábrica, e não para ser compacto:

* ``p`` lista apenas as linhas elegíveis do item — a ausência de uma linha é a
  forma de dizer "este item não roda ali";
* ``setup`` é um objeto de dois níveis, ``setup[anterior][seguinte]``, que deixa
  a assimetria visível: ``setup["TX1"]["CA1"]`` e ``setup["CA1"]["TX1"]`` são
  entradas distintas e devem mesmo ter valores diferentes;
* o setup inicial de cada linha é a entrada cujo item anterior é o nó fictício
  (``"INI"`` por padrão).

As unidades de tempo são livres (minutos, horas, turnos), desde que as mesmas em
``p``, ``setup`` e ``d``. O peso ``w`` é adimensional: só a proporção entre
pesos afeta a solução.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rubbertech.dominio import Instancia, InstanciaInvalida, Item

#: Versão do formato, gravada nos arquivos para facilitar migrações futuras.
VERSAO_FORMATO = 1


def para_dicionario(inst: Instancia, nome: str | None = None) -> dict[str, Any]:
    """Converte a instância na estrutura que será serializada em JSON."""
    setup_aninhado: dict[str, dict[str, float]] = {}
    for (anterior, seguinte), valor in inst.setup.items():
        setup_aninhado.setdefault(anterior, {})[seguinte] = valor

    return {
        "versao": VERSAO_FORMATO,
        "nome": nome or "instancia",
        "no_inicial": inst.no_inicial,
        "linhas": list(inst.linhas),
        "itens": [
            {
                "id": item.id,
                "p": dict(item.p),
                "d": item.d,
                "w": item.w,
                "cabo_aco": item.cabo_aco,
            }
            for item in inst.itens.values()
        ],
        "setup": setup_aninhado,
    }


def de_dicionario(dados: dict[str, Any]) -> Instancia:
    """Reconstrói uma instância a partir da estrutura lida do JSON.

    Erros de formato são reportados apontando o campo e o item responsáveis: um
    ``KeyError`` cru no meio da leitura de 80 itens não ajuda quem está montando
    o arquivo.
    """
    if "linhas" not in dados:
        raise InstanciaInvalida("O arquivo não tem o campo obrigatório 'linhas'.")
    if "itens" not in dados:
        raise InstanciaInvalida("O arquivo não tem o campo obrigatório 'itens'.")

    linhas = list(dados["linhas"])
    no_inicial = str(dados.get("no_inicial", "INI"))

    itens: dict[str, Item] = {}
    for posicao, bruto in enumerate(dados["itens"], start=1):
        for campo in ("id", "p", "d", "w"):
            if campo not in bruto:
                raise InstanciaInvalida(
                    f"O item na posição {posicao} não tem o campo '{campo}'."
                )
        item_id = str(bruto["id"])
        if item_id in itens:
            raise InstanciaInvalida(f"O item '{item_id}' aparece duas vezes.")
        itens[item_id] = Item(
            id=item_id,
            p={str(k): float(v) for k, v in bruto["p"].items()},
            d=float(bruto["d"]),
            w=float(bruto["w"]),
            cabo_aco=bool(bruto.get("cabo_aco", False)),
        )

    setup: dict[tuple[str, str], float] = {}
    for anterior, sucessores in dados.get("setup", {}).items():
        if not isinstance(sucessores, dict):
            raise InstanciaInvalida(
                f"O setup de '{anterior}' deveria ser um objeto "
                f"{{'item_seguinte': valor}}, e veio {type(sucessores).__name__}."
            )
        for seguinte, valor in sucessores.items():
            setup[(str(anterior), str(seguinte))] = float(valor)

    inst = Instancia(
        itens=itens, linhas=linhas, setup=setup, no_inicial=no_inicial
    )
    inst.validar()
    return inst


def salvar(inst: Instancia, caminho: str | Path, nome: str | None = None) -> Path:
    """Grava a instância em JSON (UTF-8) e devolve o caminho escrito."""
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(para_dicionario(inst, nome), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return destino


def carregar(caminho: str | Path) -> Instancia:
    """Lê uma instância de um arquivo JSON, já validada."""
    origem = Path(caminho)
    if not origem.exists():
        raise FileNotFoundError(f"Arquivo de instância não encontrado: {origem}")
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise InstanciaInvalida(
            f"O arquivo '{origem}' não é JSON válido: {erro}"
        ) from erro
    return de_dicionario(dados)
