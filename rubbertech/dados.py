"""Instância do problema: entidades, invariantes, geração e JSON.

Este módulo não importa nenhum outro do projeto, para que o modelo PLI
(:mod:`modelo`) e o avaliador independente (:mod:`conferencia`) partam
exatamente da mesma descrição do problema. Se o domínio dependesse do modelo,
um erro de modelagem se propagaria para a verificação sem deixar rastro.

Notação de três campos (Graham et al., 1979): ``R_m | s_ij, M_i | Σ w_i T_i``.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InstanciaInvalida(ValueError):
    """Erro de consistência dos dados de entrada.

    As mensagens sempre nomeiam o item ou o par responsável: um "instância
    inválida" genérico obrigaria a inspecionar 80 itens na mão.
    """


def _exigir(condicao: bool, mensagem: str) -> None:
    """Levanta :class:`InstanciaInvalida` com ``mensagem`` se ``condicao`` falhar."""
    if not condicao:
        raise InstanciaInvalida(mensagem)


# ======================================================================
# Entidades
# ======================================================================
@dataclass(frozen=True)
class Item:
    """Um item da carteira de pedidos (uma correia a produzir).

    ``p`` é um dicionário ``linha -> tempo``, e não um vetor denso: as chaves
    presentes *definem* o conjunto de linhas elegíveis (``E_i``). É isso que
    permite ao modelo não criar variáveis para pares (item, linha) impossíveis,
    o que é mais forte do que criá-las e fixá-las em zero. ``cabo_aco`` é
    informativo; a elegibilidade real vive nas chaves de ``p``.
    """

    id: str
    p: dict[str, float]
    d: float
    w: float
    cabo_aco: bool = False

    @property
    def linhas_elegiveis(self) -> tuple[str, ...]:
        """``E_i``, na ordem em que foi declarado (determinismo)."""
        return tuple(self.p)

    def tempo(self, linha: str) -> float:
        """``p[i,k]``, com erro explícito quando a linha não é elegível."""
        _exigir(
            linha in self.p,
            f"Item '{self.id}' não é elegível para a linha '{linha}' "
            f"(elegíveis: {list(self.p)}).",
        )
        return self.p[linha]

    def __hash__(self) -> int:
        """Hash pelo id: ``p`` é um dict (não hasheável) e o id já é único."""
        return hash(self.id)


@dataclass
class Tarefa:
    """Um item já alocado e datado.

    ``[inicio, fim]`` cobre apenas o processamento; o ``setup`` que a precede
    fica à parte para o relatório mostrar quanto do horizonte foi preparação.
    """

    item: str
    linha: str
    inicio: float
    fim: float
    setup: float
    atraso: float


@dataclass
class Programacao:
    """Uma solução completa. ``objetivo`` é ``Σ_i (w_i T_i + α_i A_i)``
    **recalculado**, nunca lido da função objetivo do solver."""

    sequencias: dict[str, list[str]]
    tarefas: list[Tarefa]
    objetivo: float

    def tarefa(self, item: str) -> Tarefa:
        for tarefa in self.tarefas:
            if tarefa.item == item:
                return tarefa
        raise KeyError(f"Item '{item}' não está na programação.")

    def tarefas_da_linha(self, linha: str) -> list[Tarefa]:
        """Tarefas de uma linha, em ordem cronológica."""
        return sorted((t for t in self.tarefas if t.linha == linha), key=lambda t: t.inicio)


@dataclass
class Instancia:
    """Uma instância completa de ``R_m | s_ij, M_i | Σ w_i T_i``.

    ``setup[(i, j)]`` é a preparação para produzir ``j`` logo depois de ``i``. A
    matriz é **assimétrica** (``s[i,j] != s[j,i]``), o que dá a cada linha a
    estrutura de um Caixeiro Viajante assimétrico. Quando ``i`` é o nó fictício
    :attr:`no_inicial`, o valor é o setup inicial da linha; o rótulo é atributo,
    e não a constante ``"0"``, para nunca colidir com o id de um item real.
    """

    itens: dict[str, Item]
    linhas: list[str]
    setup: dict[tuple[str, str], float]
    no_inicial: str = "INI"

    # ---- conjuntos da formulação -------------------------------------
    @property
    def J(self) -> list[str]:
        """Conjunto ``J`` dos itens."""
        return list(self.itens)

    @property
    def J0(self) -> list[str]:
        """``J0 = J ∪ {0}``, com o nó fictício na frente."""
        return [self.no_inicial, *self.itens]

    @property
    def M(self) -> list[str]:
        """Conjunto ``M`` das linhas."""
        return list(self.linhas)

    @property
    def n(self) -> int:
        """``n = |J|``, usado no big-M das restrições MTZ."""
        return len(self.itens)

    def elegiveis(self, i: str) -> tuple[str, ...]:
        """``E_i``."""
        return self.itens[i].linhas_elegiveis

    def p(self, i: str, k: str) -> float:
        """``p[i,k]``."""
        return self.itens[i].tempo(k)

    def s(self, i: str, j: str) -> float:
        """``s[i,j]``, com erro explícito quando o par não foi definido."""
        _exigir((i, j) in self.setup, f"Setup ausente para o par ('{i}', '{j}').")
        return self.setup[(i, j)]

    # ---- estrutura do grafo de sequenciamento ------------------------
    def arcos(self) -> Iterator[tuple[str, str, str]]:
        """Trios ``(i, j, k)`` para os quais ``y[i,j,k]`` deve existir.

        Um arco é válido quando ``i != j``, ``k`` é elegível para o sucessor
        ``j``, e o predecessor ``i`` ou é o nó fictício ou também é elegível
        para ``k``. Não gerar os demais é o principal redutor de tamanho do
        modelo: com ~1/4 da carteira presa à Linha 4, a diferença para o grafo
        completo é de várias vezes.
        """
        for j in self.itens:
            for k in self.elegiveis(j):
                for i in self.J0:
                    if i != j and (i == self.no_inicial or k in self.elegiveis(i)):
                        yield (i, j, k)

    def pares_de_setup(self) -> set[tuple[str, str]]:
        """Pares ``(i, j)`` cujo setup é efetivamente necessário ao modelo."""
        return {(i, j) for i, j, _ in self.arcos()}

    def big_m(self) -> float:
        """Calcula ``V`` a partir dos dados, em vez de arbitrar um número::

            V = Σ_i ( max_{k∈E_i} p[i,k] + max_{a≠i} s[a,i] ) + max_i d[i]

        A primeira parcela limita superiormente a conclusão do último item de
        qualquer linha (tudo em série, sempre com o pior tempo e o pior setup de
        entrada); a segunda cobre o termo ``- d[i]`` das restrições de atraso.

        Com um ``V`` exagerado o modelo continua **correto**, mas a relaxação
        linear de (4) e (4') fica frouxa — um ``y`` fracionário compra a
        desativação da restrição quase de graça — e o limite inferior do
        branch-and-bound desaba. Em 80 itens é a diferença entre resolver e não.
        """
        total = 0.0
        for i, item in self.itens.items():
            maior_s = max(
                (v for (o, dst), v in self.setup.items() if dst == i and o != i),
                default=0.0,
            )
            total += max(item.p.values(), default=0.0) + maior_s
        return total + max((item.d for item in self.itens.values()), default=0.0)

    # ---- validação ---------------------------------------------------
    def validar(self) -> None:
        """Verifica as invariantes; não retorna nada, ou levanta erro.

        Roda antes de qualquer construção de modelo: um setup faltando vira, no
        PuLP, um ``KeyError`` no meio de milhares de restrições, e a mensagem
        resultante não ajuda ninguém.
        """
        _exigir(bool(self.itens), "A instância não possui itens.")
        _exigir(bool(self.linhas), "A instância não possui linhas de produção.")
        _exigir(
            len(set(self.linhas)) == len(self.linhas),
            f"Há linhas repetidas em 'linhas': {self.linhas}.",
        )
        _exigir(
            self.no_inicial not in self.itens,
            f"O nó fictício '{self.no_inicial}' colide com o id de um item.",
        )

        for chave, item in self.itens.items():
            _exigir(
                chave == item.id,
                f"Chave '{chave}' do dicionário de itens não corresponde ao id "
                f"'{item.id}'.",
            )
            _exigir(
                bool(item.p), f"Item '{item.id}' não possui nenhuma linha elegível."
            )
            for linha, tempo in item.p.items():
                _exigir(
                    linha in self.linhas,
                    f"Item '{item.id}' declara tempo na linha '{linha}', que não "
                    f"existe na instância (linhas: {self.linhas}).",
                )
                _exigir(
                    tempo is not None and math.isfinite(tempo) and tempo > 0,
                    f"Tempo de processamento inválido para o par "
                    f"('{item.id}', '{linha}'): {tempo!r}.",
                )
            _exigir(item.d >= 0, f"Item '{item.id}' tem prazo negativo: d = {item.d}.")
            _exigir(
                item.w >= 0,
                f"Item '{item.id}' tem peso negativo: w = {item.w}. Pesos negativos "
                "invalidariam a linearização de T.",
            )

        for i, j in sorted(self.pares_de_setup()):
            _exigir(
                (i, j) in self.setup,
                f"Setup ausente para o par ('{i}', '{j}'), necessário porque existe "
                "arco válido entre esses itens.",
            )
            valor = self.setup[(i, j)]
            _exigir(
                valor is not None and math.isfinite(valor) and valor >= 0,
                f"Setup inválido para o par ('{i}', '{j}'): {valor!r}.",
            )


# ======================================================================
# Geração de instâncias
# ======================================================================
#: Prefixos: itens com cabo de aço (linha dedicada) e têxteis (linhas livres).
PREFIXO_CABO_ACO, PREFIXO_TEXTIL = "CA", "TX"

#: Setups, em unidades de tempo. A assimetria não é artifício para deixar o
#: problema difícil: montar o dispositivo de tração dos cabos (TX->CA) custa
#: mais do que desmontá-lo e limpar a linha (CA->TX). É essa diferença que faz
#: de cada linha um Caixeiro Viajante assimétrico e impede resolver o
#: sequenciamento com uma regra de ordenação simples.
SETUP_INICIAL_CABO_ACO, SETUP_INICIAL_TEXTIL = 12.0, 8.0
SETUP_INTRAFAMILIA = 5.0
SETUP_TEXTIL_PARA_CABO, SETUP_CABO_PARA_TEXTIL = 20.0, 11.0
#: Setup inicial punitivo da armadilha de subciclo (ver :func:`gerar`).
SETUP_INICIAL_ARMADILHA = 40.0

#: As quatro linhas paralelas. O fator de velocidade multiplica o tempo-base do
#: item (maior = mais lenta): é o que torna o problema `R_m` e não `P_m`. A L4,
#: robusta para cabo de aço, é a mais lenta para têxteis.
LINHAS_PADRAO = ["L1", "L2", "L3", "L4"]
FATOR_VELOCIDADE = {"L1": 1.00, "L2": 1.15, "L3": 1.25, "L4": 1.40}

#: Faixa do tempo-base de processamento (na linha mais rápida).
TEMPO_BASE_MINIMO, TEMPO_BASE_MAXIMO = 15.0, 40.0
#: Prazos: ``d_i ~ U(H(folga - disp/2), H(folga + disp/2))``, com ``H`` o
#: horizonte estimado de uma linha. Com folga 0,45 os prazos caem no meio do
#: horizonte, e não no fim — se caíssem no fim quase tudo ficaria pronto no
#: prazo, o ótimo seria zero e a instância não distinguiria um modelo certo de
#: um errado. A dispersão larga cria a tensão entre item urgente e item caro,
#: que é onde a otimização decide.
FOLGA_PRAZO_MEDIA, FOLGA_PRAZO_DISPERSAO = 0.45, 0.70
#: Pesos possíveis (multa contratual × criticidade do cliente).
PESOS_POSSIVEIS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
PESOS_PROBABILIDADES = [0.22, 0.20, 0.17, 0.14, 0.12, 0.09, 0.06]
#: Fração da carteira com cabo de aço no caso real da fábrica.
FRACAO_CABO_ACO_PADRAO = 0.25


def familia(item_id: str) -> str:
    """Família tecnológica do item, deduzida do prefixo do identificador."""
    return PREFIXO_CABO_ACO if item_id.startswith(PREFIXO_CABO_ACO) else PREFIXO_TEXTIL


def montar_setup(ids: list[str], no_inicial: str = "INI") -> dict[tuple[str, str], float]:
    """Matriz de setup completa e assimétrica, derivada das famílias."""
    setup = {
        (no_inicial, j): (
            SETUP_INICIAL_CABO_ACO
            if familia(j) == PREFIXO_CABO_ACO
            else SETUP_INICIAL_TEXTIL
        )
        for j in ids
    }
    for i in ids:
        for j in ids:
            if i == j:
                continue
            if familia(i) == familia(j):
                setup[(i, j)] = SETUP_INTRAFAMILIA
            elif familia(j) == PREFIXO_CABO_ACO:
                setup[(i, j)] = SETUP_TEXTIL_PARA_CABO
            else:
                setup[(i, j)] = SETUP_CABO_PARA_TEXTIL
    return setup


def gerar(
    n: int,
    m: int = 4,
    frac_cabo: float = FRACAO_CABO_ACO_PADRAO,
    com_setup: bool = True,
    seed: int = 0,
    armadilha_subciclo: float | None = None,
) -> Instancia:
    """Gerador único e determinístico de instâncias, já validadas.

    Os quatro estágios da validação incremental são combinações de argumentos
    (ver ``main.py validar`` e a tabela do README), e não funções distintas::

        estágio 1   gerar(5, m=1, frac_cabo=0, com_setup=False)
        estágio 2   gerar(5, m=1, frac_cabo=0.4)
        estágio 3   gerar(5, m=1, frac_cabo=0.4, armadilha_subciclo=40)
        estágio 4   gerar(5, m=3, frac_cabo=0.4)

    ``m`` usa as ``m`` primeiras de :data:`LINHAS_PADRAO`, e a última delas é a
    linha dedicada a cabo de aço. ``com_setup=False`` zera a matriz inteira.
    ``seed`` garante reprodutibilidade — determinismo importa mais que realismo
    aqui, porque os experimentos do relatório precisam ser repetíveis.

    ``armadilha_subciclo``, quando dado, substitui a matriz de setup por uma
    armadilha: entrar na linha custa esse valor e trocar de um item para outro é
    de graça. Um modelo sem eliminação de subciclos acha ótimo fechar um ciclo
    entre os itens e nunca pagar o setup inicial — solução que existe no grafo
    mas não no chão de fábrica. É o único parâmetro que sobreviveu à unificação
    dos geradores, porque essa estrutura de custos não é expressável pelas
    famílias de itens.
    """
    _exigir(n >= 1, f"A instância precisa de ao menos um item (n={n}).")
    _exigir(
        1 <= m <= len(LINHAS_PADRAO),
        f"m deve estar entre 1 e {len(LINHAS_PADRAO)} (recebido: {m}).",
    )

    rng = random.Random(seed)
    linhas = LINHAS_PADRAO[:m]
    linha_cabo = linhas[-1]
    quantidade_cabo = round(n * frac_cabo)

    # Tempos: tempo-base sorteado × fator de velocidade da linha. É assim que as
    # máquinas ficam paralelas **não relacionadas** sem que virem ruído puro.
    especificacoes: list[tuple[str, bool, dict[str, float]]] = []
    for indice in range(1, n + 1):
        cabo_aco = indice <= quantidade_cabo
        base = rng.uniform(TEMPO_BASE_MINIMO, TEMPO_BASE_MAXIMO)
        elegiveis = [linha_cabo] if cabo_aco else linhas
        prefixo = PREFIXO_CABO_ACO if cabo_aco else PREFIXO_TEXTIL
        tempos = {k: round(base * FATOR_VELOCIDADE[k], 1) for k in elegiveis}
        especificacoes.append((f"{prefixo}{indice}", cabo_aco, tempos))

    # Horizonte de uma linha: carga total mais um setup típico por item. A
    # ordem das condições espelha a que monta o `setup` de fato mais abaixo,
    # para as duas nunca discordarem sobre qual estrutura de custo vale.
    if armadilha_subciclo is not None:
        setup_tipico = armadilha_subciclo / n
    elif not com_setup:
        setup_tipico = 0.0
    elif frac_cabo:
        setup_tipico = (SETUP_INTRAFAMILIA + SETUP_TEXTIL_PARA_CABO) / 2
    else:
        setup_tipico = SETUP_INTRAFAMILIA
    carga = sum(sum(t.values()) / len(t) for _, _, t in especificacoes)
    horizonte = (carga + n * setup_tipico) / m
    minimo = horizonte * max(FOLGA_PRAZO_MEDIA - FOLGA_PRAZO_DISPERSAO / 2, 0.05)
    maximo = horizonte * (FOLGA_PRAZO_MEDIA + FOLGA_PRAZO_DISPERSAO / 2)

    itens = {
        item_id: Item(
            id=item_id,
            p=tempos,
            d=round(rng.uniform(minimo, maximo), 1),
            w=rng.choices(PESOS_POSSIVEIS, weights=PESOS_PROBABILIDADES, k=1)[0],
            cabo_aco=cabo_aco,
        )
        for item_id, cabo_aco, tempos in especificacoes
    }

    ids = list(itens)
    if armadilha_subciclo is not None:
        setup = {("INI", j): float(armadilha_subciclo) for j in ids}
        setup.update({(i, j): 0.0 for i in ids for j in ids if i != j})
    elif not com_setup:
        setup = {(a, j): 0.0 for j in ids for a in ["INI", *ids] if a != j}
    else:
        setup = montar_setup(ids)

    inst = Instancia(itens=itens, linhas=linhas, setup=setup)
    inst.validar()
    return inst


# ======================================================================
# Instância de referência (âncora de regressão)
# ======================================================================
#: ``id -> (tempos por linha elegível, prazo, peso)``. A ausência de uma linha
#: em ``p`` é o que codifica ``E_i``: CA1 e CA2 só rodam na L4.
_REFERENCIA: dict[str, tuple[dict[str, float], float, float]] = {
    "CA1": ({"L4": 39.0}, 45.0, 8.0),
    "CA2": ({"L4": 48.0}, 95.0, 2.0),
    "TX3": ({"L1": 20.0, "L2": 23.0, "L3": 25.0, "L4": 28.0}, 40.0, 5.0),
    "TX4": ({"L1": 16.0, "L2": 18.0, "L3": 20.0, "L4": 22.0}, 30.0, 3.0),
    "TX5": ({"L1": 24.0, "L2": 28.0, "L3": 30.0, "L4": 34.0}, 50.0, 1.0),
    "TX6": ({"L1": 18.0, "L2": 21.0, "L3": 22.0, "L4": 25.0}, 35.0, 6.0),
    "TX7": ({"L1": 22.0, "L2": 25.0, "L3": 27.0, "L4": 31.0}, 55.0, 2.0),
    "TX8": ({"L1": 26.0, "L2": 30.0, "L3": 32.0, "L4": 36.0}, 42.0, 4.0),
}

#: Ótimo da instância de referência, verificado por enumeração exaustiva.
OTIMO_REFERENCIA = 144.0

#: Programação ótima documentada no relatório. Há ótimos alternativos de mesmo
#: custo (trocar TX3 e TX8 entre L1 e L3); esta é a que o texto exibe.
PROGRAMACAO_REFERENCIA = {
    "L1": ["TX4", "TX3"],
    "L2": ["TX6", "TX7"],
    "L3": ["TX8", "TX5"],
    "L4": ["CA1", "CA2"],
}


def instancia_referencia() -> Instancia:
    """Instância de 8 itens e 4 linhas usada como teste de regressão.

    O ótimo é ``Z = 144,0``. O detalhe que interessa: ele deixa TX5 atrasar 25
    u.t. porque seu peso é 1, e protege TX6 (peso 6) e TX4 (peso 3). Uma
    implementação que "espalhe" o atraso está minimizando a coisa errada.
    """
    itens = {
        item_id: Item(
            id=item_id,
            p=dict(tempos),
            d=prazo,
            w=peso,
            cabo_aco=familia(item_id) == PREFIXO_CABO_ACO,
        )
        for item_id, (tempos, prazo, peso) in _REFERENCIA.items()
    }
    inst = Instancia(
        itens=itens, linhas=list(LINHAS_PADRAO), setup=montar_setup(list(itens))
    )
    inst.validar()
    return inst


# ======================================================================
# Persistência em JSON
# ======================================================================
# O formato foi escolhido para ser escrito **à mão** por quem tem os dados da
# fábrica, e não para ser compacto: ``p`` lista apenas as linhas elegíveis do
# item (a ausência de uma linha diz "não roda ali"); ``setup`` é um objeto de
# dois níveis ``setup[anterior][seguinte]``, que deixa a assimetria visível; e o
# setup inicial de cada linha é a entrada cujo anterior é o nó fictício. As
# unidades de tempo são livres, desde que as mesmas em ``p``, ``setup`` e ``d``;
# ``w`` é adimensional, só a proporção entre pesos afeta a solução.

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
            {"id": i.id, "p": dict(i.p), "d": i.d, "w": i.w, "cabo_aco": i.cabo_aco}
            for i in inst.itens.values()
        ],
        "setup": setup_aninhado,
    }


def de_dicionario(dados: dict[str, Any]) -> Instancia:
    """Reconstrói uma instância a partir da estrutura lida do JSON.

    Erros de formato apontam o campo e o item responsáveis: um ``KeyError`` cru
    no meio da leitura de 80 itens não ajuda quem está montando o arquivo.
    """
    for campo in ("linhas", "itens"):
        _exigir(campo in dados, f"O arquivo não tem o campo obrigatório '{campo}'.")

    itens: dict[str, Item] = {}
    for posicao, bruto in enumerate(dados["itens"], start=1):
        for campo in ("id", "p", "d", "w"):
            _exigir(
                campo in bruto,
                f"O item na posição {posicao} não tem o campo '{campo}'.",
            )
        item_id = str(bruto["id"])
        _exigir(item_id not in itens, f"O item '{item_id}' aparece duas vezes.")
        itens[item_id] = Item(
            id=item_id,
            p={str(k): float(v) for k, v in bruto["p"].items()},
            d=float(bruto["d"]),
            w=float(bruto["w"]),
            cabo_aco=bool(bruto.get("cabo_aco", False)),
        )

    setup: dict[tuple[str, str], float] = {}
    for anterior, sucessores in dados.get("setup", {}).items():
        _exigir(
            isinstance(sucessores, dict),
            f"O setup de '{anterior}' deveria ser um objeto "
            f"{{'item_seguinte': valor}}, e veio {type(sucessores).__name__}.",
        )
        for seguinte, valor in sucessores.items():
            setup[(str(anterior), str(seguinte))] = float(valor)

    inst = Instancia(
        itens=itens,
        linhas=list(dados["linhas"]),
        setup=setup,
        no_inicial=str(dados.get("no_inicial", "INI")),
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
        return de_dicionario(json.loads(origem.read_text(encoding="utf-8")))
    except json.JSONDecodeError as erro:
        raise InstanciaInvalida(
            f"O arquivo '{origem}' não é JSON válido: {erro}"
        ) from erro
