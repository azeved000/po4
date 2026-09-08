"""Geradores determinísticos de instâncias, um por estágio da validação.

Todos os geradores recebem uma `seed` e devolvem uma :class:`Instancia` já
validada. Determinismo importa mais aqui do que realismo: os experimentos do
relatório precisam ser reproduzíveis por quem ler o trabalho.

Os parâmetros numéricos do processo (fatores de velocidade das linhas, setups
por família, folga dos prazos, distribuição dos pesos) estão em constantes
nomeadas logo abaixo, e não espalhados no corpo das funções — é isso que
permite ao relatório citar os números da geração sem ter que ler o código.
"""

from __future__ import annotations

import random

from rubbertech.dominio import Instancia, Item

# ----------------------------------------------------------------------
# Prefixos de identificação e famílias
# ----------------------------------------------------------------------
#: Prefixo dos itens com cabo de aço (só produzíveis na linha dedicada).
PREFIXO_CABO_ACO = "CA"
#: Prefixo dos itens têxteis (produzíveis em qualquer linha).
PREFIXO_TEXTIL = "TX"

# ----------------------------------------------------------------------
# Setups (unidades de tempo)
# ----------------------------------------------------------------------
#: Setup inicial de linha para um item com cabo de aço.
SETUP_INICIAL_CABO_ACO = 12.0
#: Setup inicial de linha para um item têxtil.
SETUP_INICIAL_TEXTIL = 8.0
#: Troca entre itens da mesma família: só ajuste fino de largura e tensão.
SETUP_INTRAFAMILIA = 5.0
#: Têxtil -> cabo de aço: montar o dispositivo de tração dos cabos. É o caro.
SETUP_TEXTIL_PARA_CABO = 20.0
#: Cabo de aço -> têxtil: desmontar e limpar. Mais barato que montar.
SETUP_CABO_PARA_TEXTIL = 11.0

# ----------------------------------------------------------------------
# Linhas de produção
# ----------------------------------------------------------------------
#: Nomes das quatro linhas paralelas da fábrica.
LINHAS_PADRAO = ["L1", "L2", "L3", "L4"]
#: Única linha equipada para itens com cabo de aço.
LINHA_CABO_ACO = "L4"
#: Fator de velocidade por linha: multiplica o tempo-base do item. Maior = mais
#: lenta. As linhas não são idênticas — é o que torna o problema `R_m` e não
#: `P_m`; a L4, mais robusta para cabo de aço, é a mais lenta para têxteis.
FATOR_VELOCIDADE = {"L1": 1.00, "L2": 1.15, "L3": 1.25, "L4": 1.40}

# ----------------------------------------------------------------------
# Carteira de pedidos
# ----------------------------------------------------------------------
#: Faixa do tempo-base de processamento (na linha mais rápida).
TEMPO_BASE_MINIMO = 15.0
TEMPO_BASE_MAXIMO = 40.0
#: Fração da carteira com cabo de aço (~1/4 no caso real da fábrica).
FRACAO_CABO_ACO_PADRAO = 0.25
#: Folga média dos prazos, como fração do horizonte de produção de uma linha
#: (carga total dividida pelo número de linhas). É o esquema clássico dos
#: geradores de instâncias de atraso ponderado: prazo médio = folga × horizonte.
#: Com 0,45 os prazos caem no meio do horizonte, e não no fim — se caíssem no
#: fim, quase tudo ficaria pronto no prazo, o ótimo seria zero e a instância não
#: distinguiria um modelo certo de um errado.
FOLGA_PRAZO_MEDIA = 0.45
#: Amplitude relativa dos prazos: eles são sorteados uniformemente em
#: ``horizonte × (folga_media ± dispersao/2)``. Uma amplitude larga é o que cria
#: a tensão entre itens urgentes e itens caros, que é onde a otimização decide.
FOLGA_PRAZO_DISPERSAO = 0.70
#: Pesos possíveis (multa × criticidade do cliente) e suas probabilidades.
PESOS_POSSIVEIS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
PESOS_PROBABILIDADES = [0.22, 0.20, 0.17, 0.14, 0.12, 0.09, 0.06]

# ----------------------------------------------------------------------
# Carteira de clientes
# ----------------------------------------------------------------------
#: Clientes fictícios da fábrica, cada um com sua criticidade — o peso ``w`` dos
#: pedidos daquele cliente. A criticidade é **propriedade do cliente**, e não do
#: pedido: um cliente crítico é crítico em todos os seus pedidos.
#:
#: Isso não é detalhe cosmético. Se os pesos fossem sorteados por pedido, o
#: modelo veria uma carteira em que cada atraso é um evento isolado. Sorteados
#: por cliente, vários pedidos passam a compartilhar o mesmo peso alto, e
#: proteger um cliente vira uma decisão que arrasta várias alocações ao mesmo
#: tempo — que é o que acontece na fábrica de verdade.
CLIENTES_PADRAO: list[tuple[str, float]] = [
    ("Adriana Prado", 8.0),
    ("Bruno Cavalcanti", 6.0),
    ("Camila Fontes", 5.0),
    ("Diego Vasconcelos", 4.0),
    ("Eduarda Nogueira", 3.0),
    ("Fábio Assunção", 2.0),
    ("Gabriela Munhoz", 1.0),
    ("Henrique Salles", 8.0),
    ("Isabela Tavares", 5.0),
    ("Joaquim Bettencourt", 4.0),
    ("Karina Delgado", 3.0),
    ("Leonardo Whitaker", 2.0),
    ("Mariana Yamamoto", 6.0),
    ("Norberto Aguiar", 1.0),
    ("Otávia Rezende", 4.0),
    ("Paulo Sarmento", 2.0),
]

#: Quantos pedidos, em média, cada cliente coloca na carteira. Acima de 1 os
#: clientes se repetem, que é o caso interessante.
PEDIDOS_POR_CLIENTE = 2.5


def familia(item_id: str) -> str:
    """Família tecnológica do item, deduzida do prefixo do identificador."""
    return PREFIXO_CABO_ACO if item_id.startswith(PREFIXO_CABO_ACO) else PREFIXO_TEXTIL


def montar_setup(
    ids: list[str],
    no_inicial: str = "INI",
    intrafamilia: float = SETUP_INTRAFAMILIA,
    textil_para_cabo: float = SETUP_TEXTIL_PARA_CABO,
    cabo_para_textil: float = SETUP_CABO_PARA_TEXTIL,
    inicial_cabo: float = SETUP_INICIAL_CABO_ACO,
    inicial_textil: float = SETUP_INICIAL_TEXTIL,
) -> dict[tuple[str, str], float]:
    """Matriz de setup completa e **assimétrica**, derivada das famílias.

    A assimetria não é um artifício para deixar o problema difícil: montar o
    dispositivo de tração dos cabos (TX→CA) custa mais do que desmontá-lo e
    limpar a linha (CA→TX). É essa diferença que faz de cada linha um Problema
    do Caixeiro Viajante assimétrico e que impede resolver o sequenciamento com
    uma regra de ordenação simples.
    """
    setup: dict[tuple[str, str], float] = {}
    for j in ids:
        setup[(no_inicial, j)] = (
            inicial_cabo if familia(j) == PREFIXO_CABO_ACO else inicial_textil
        )
    for i in ids:
        for j in ids:
            if i == j:
                continue
            if familia(i) == familia(j):
                setup[(i, j)] = intrafamilia
            elif familia(j) == PREFIXO_CABO_ACO:
                setup[(i, j)] = textil_para_cabo
            else:
                setup[(i, j)] = cabo_para_textil
    return setup


# ======================================================================
# Construção genérica de carteiras
# ======================================================================
def _identificador(indice: int, cabo_aco: bool) -> str:
    """Ids no padrão do chão de fábrica: ``CA7`` (cabo de aço), ``TX7`` (têxtil)."""
    prefixo = PREFIXO_CABO_ACO if cabo_aco else PREFIXO_TEXTIL
    return f"{prefixo}{indice}"


def gerar_carteira(
    n: int,
    linhas: list[str],
    seed: int,
    frac_cabo: float = 0.0,
    linha_cabo: str = LINHA_CABO_ACO,
    folga_media: float = FOLGA_PRAZO_MEDIA,
    folga_dispersao: float = FOLGA_PRAZO_DISPERSAO,
    fator_velocidade: dict[str, float] | None = None,
    setup_tipico: float | None = None,
    pesos: list[float] | None = None,
    pesos_probabilidades: list[float] | None = None,
    clientes: list[tuple[str, float]] | None = None,
    pedidos_por_cliente: float = PEDIDOS_POR_CLIENTE,
) -> dict[str, Item]:
    """Gera ``n`` itens determinísticos a partir de ``seed``.

    O tempo de processamento de um item é um tempo-base sorteado, multiplicado
    pelo fator de velocidade da linha — é assim que as máquinas ficam paralelas
    **não relacionadas** sem que os tempos virem ruído puro.

    Os prazos seguem o esquema usual dos geradores de instâncias de atraso
    ponderado: estima-se o horizonte ``H`` (carga total, mais um setup típico
    por item, dividida pelo número de linhas) e sorteia-se
    ``d_i ~ U(H·(folga_media - dispersão/2), H·(folga_media + dispersão/2))``.
    Espalhar os prazos ao longo do horizonte, em vez de concentrá-los no fim, é
    o que garante que a instância seja estruturalmente atrasada — com prazos
    folgados o ótimo é zero e a instância não distingue um modelo certo de um
    errado.

    Cada pedido é atribuído a um cliente sorteado de ``clientes`` (padrão:
    :data:`CLIENTES_PADRAO`), e o peso ``w`` do pedido é a **criticidade desse
    cliente**. O número de clientes é ``n / pedidos_por_cliente``, de modo que a
    carteira tenha clientes repetidos — vários pedidos do mesmo cliente,
    compartilhando o mesmo peso, como numa carteira real.

    ``pesos`` e ``pesos_probabilidades`` desligam esse acoplamento e voltam ao
    sorteio de peso independente por pedido: ``pesos=[1.0]`` produz a carteira de
    pesos uniformes, em que o objetivo degenera no atraso total simples — um caso
    de borda útil para testar se a ponderação está mesmo sendo aplicada.
    """
    rng = random.Random(seed)
    fator = fator_velocidade or FATOR_VELOCIDADE
    quantidade_cabo = round(n * frac_cabo)
    valores_de_peso = pesos or PESOS_POSSIVEIS
    probabilidades = pesos_probabilidades or (
        PESOS_PROBABILIDADES if valores_de_peso is PESOS_POSSIVEIS else None
    )
    # Recorta a carteira de clientes para o tamanho do pedido: com poucos itens,
    # poucos clientes — senão cada pedido teria um cliente diferente e a
    # repetição, que é o ponto, desapareceria.
    #
    # O sorteio é `sample` e não uma fatia do início da lista: como o catálogo
    # está ordenado por criticidade decrescente, pegar os primeiros faria toda
    # carteira pequena ser formada só pelos clientes mais críticos, sem nenhum
    # cliente barato para o modelo sacrificar. O viés apareceria como instâncias
    # pequenas artificialmente caras e sem trade-off interessante.
    catalogo = list(clientes if clientes is not None else CLIENTES_PADRAO)
    quantidade_clientes = max(
        1, min(len(catalogo), round(n / max(pedidos_por_cliente, 0.01)))
    )
    carteira_clientes = rng.sample(catalogo, quantidade_clientes)

    especificacoes: list[tuple[str, bool, dict[str, float]]] = []
    for indice in range(1, n + 1):
        cabo_aco = indice <= quantidade_cabo
        item_id = _identificador(indice, cabo_aco)
        base = rng.uniform(TEMPO_BASE_MINIMO, TEMPO_BASE_MAXIMO)
        elegiveis = [linha_cabo] if cabo_aco else list(linhas)
        tempos = {k: round(base * fator.get(k, 1.0), 1) for k in elegiveis}
        especificacoes.append((item_id, cabo_aco, tempos))

    carga_total = sum(
        sum(tempos.values()) / len(tempos) for _, _, tempos in especificacoes
    )
    if setup_tipico is None:
        setup_tipico = (
            (SETUP_INTRAFAMILIA + SETUP_TEXTIL_PARA_CABO) / 2
            if frac_cabo
            else SETUP_INTRAFAMILIA
        )
    horizonte = (carga_total + n * setup_tipico) / max(len(linhas), 1)
    prazo_minimo = horizonte * max(folga_media - folga_dispersao / 2, 0.05)
    prazo_maximo = horizonte * (folga_media + folga_dispersao / 2)

    itens: dict[str, Item] = {}
    for item_id, cabo_aco, tempos in especificacoes:
        prazo = round(rng.uniform(prazo_minimo, prazo_maximo), 1)
        nome_cliente, criticidade = rng.choice(carteira_clientes)
        # Com `pesos` explícito, o peso volta a ser sorteado por pedido; sem
        # ele, o peso É a criticidade do cliente que fez o pedido.
        peso = (
            rng.choices(valores_de_peso, weights=probabilidades, k=1)[0]
            if pesos is not None
            else criticidade
        )
        itens[item_id] = Item(
            id=item_id,
            p=tempos,
            d=prazo,
            w=peso,
            cabo_aco=cabo_aco,
            cliente=nome_cliente,
        )
    return itens


# ======================================================================
# Estágios da validação incremental
# ======================================================================
def estagio_1_maquina_unica(n: int = 5, seed: int = 1) -> Instancia:
    """Estágio 1 — uma linha, setup zero.

    O caso mais simples que ainda é o problema certo (``1 | | Σ w_i T_i``).
    Serve para confirmar que o solver acha o ótimo trivial e que a datação por
    big-M não introduz atraso fantasma quando não há preparação nenhuma.
    """
    itens = gerar_carteira(n, ["L1"], seed=seed, setup_tipico=0.0)
    ids = list(itens)
    setup = {(no, j): 0.0 for j in ids for no in ["INI", *ids] if no != j}
    inst = Instancia(itens=itens, linhas=["L1"], setup=setup)
    inst.validar()
    return inst


def estagio_2_setup(n: int = 5, seed: int = 2) -> Instancia:
    """Estágio 2 — uma linha, setup dependente da sequência e assimétrico.

    Mistura as duas famílias na mesma linha para que ``s[i,j] != s[j,i]`` pese
    de fato. Valida o timing do setup (ele entra antes do processamento, não
    depois) e a assimetria: inverter dois itens tem que mudar o custo.
    """
    itens = gerar_carteira(n, ["L1"], seed=seed, frac_cabo=0.4, linha_cabo="L1")
    inst = Instancia(itens=itens, linhas=["L1"], setup=montar_setup(list(itens)))
    inst.validar()
    return inst


#: Setup inicial punitivo do estágio 3: torna atraente "começar do nada".
SETUP_INICIAL_ARMADILHA = 40.0


def estagio_3_subciclos(n: int = 5, seed: int = 3) -> Instancia:
    """Estágio 3 — uma linha, matriz de setup que convida ao subciclo.

    A armadilha: entrar na linha custa ``SETUP_INICIAL_ARMADILHA``, enquanto
    trocar de um item para outro é de graça. Um modelo sem eliminação de
    subciclos acha ótimo fechar um ciclo entre os itens e nunca pagar o setup
    inicial — solução que existe no grafo mas não no chão de fábrica.

    Aqui só as restrições (4') seguram o modelo (um ciclo implicaria
    ``C[i] > C[i]``); é exatamente o cenário em que uma falha na datação por
    big-M aparece como programação incompleta na extração da solução.
    """
    itens = gerar_carteira(
        n, ["L1"], seed=seed, setup_tipico=SETUP_INICIAL_ARMADILHA / n
    )
    ids = list(itens)
    setup: dict[tuple[str, str], float] = {
        ("INI", j): SETUP_INICIAL_ARMADILHA for j in ids
    }
    setup.update({(i, j): 0.0 for i in ids for j in ids if i != j})
    inst = Instancia(itens=itens, linhas=["L1"], setup=setup)
    inst.validar()
    return inst


def estagio_4_elegibilidade(
    n: int = 6, m: int = 3, frac_cabo: float = 0.34, seed: int = 4
) -> Instancia:
    """Estágio 4 — várias linhas com elegibilidade restrita.

    Parte da carteira só roda na linha dedicada a cabo de aço. Valida que o
    modelo não cria nem usa variáveis para pares (item, linha) impossíveis e que
    a linha dedicada vira gargalo — o efeito que o relatório precisa mostrar.
    """
    linhas = LINHAS_PADRAO[:m]
    linha_cabo = linhas[-1]
    itens = gerar_carteira(
        n, linhas, seed=seed, frac_cabo=frac_cabo, linha_cabo=linha_cabo
    )
    inst = Instancia(itens=itens, linhas=linhas, setup=montar_setup(list(itens)))
    inst.validar()
    return inst


def estagio_5_intermediario(seed: int = 5, n: int = 20) -> Instancia:
    """Estágio 5 — ~20 itens, 4 linhas: já é grande demais para força bruta.

    A partir daqui a conferência deixa de ser "o modelo bate com a enumeração" e
    passa a ser "o modelo bate com o avaliador independente e o solver reporta
    o gap honestamente". É o estágio que mede o desempenho do solver.
    """
    itens = gerar_carteira(
        n, LINHAS_PADRAO, seed=seed, frac_cabo=FRACAO_CABO_ACO_PADRAO
    )
    inst = Instancia(
        itens=itens, linhas=list(LINHAS_PADRAO), setup=montar_setup(list(itens))
    )
    inst.validar()
    return inst


def estagio_6_completo(seed: int = 6, n: int = 80) -> Instancia:
    """Estágio 6 — ~80 itens em 4 linhas: a carteira real da fábrica.

    Cerca de 1/4 dos itens tem cabo de aço e disputa a Linha 4. Nesta escala o
    CBC dificilmente prova otimalidade no tempo disponível; o que se relata é a
    melhor solução encontrada **com o gap declarado**.
    """
    itens = gerar_carteira(
        n, LINHAS_PADRAO, seed=seed, frac_cabo=FRACAO_CABO_ACO_PADRAO
    )
    inst = Instancia(
        itens=itens, linhas=list(LINHAS_PADRAO), setup=montar_setup(list(itens))
    )
    inst.validar()
    return inst


#: Geradores expostos ao CLI e aos scripts, por nome.
GERADORES = {
    "estagio_1": estagio_1_maquina_unica,
    "estagio_2": estagio_2_setup,
    "estagio_3": estagio_3_subciclos,
    "estagio_4": estagio_4_elegibilidade,
    "estagio_5": estagio_5_intermediario,
    "estagio_6": estagio_6_completo,
    "referencia": lambda: instancia_referencia(),
}


# ======================================================================
# Instância de referência (teste de regressão)
# ======================================================================
#: Tempos de processamento da instância de referência. Um `None` marca linha
#: inelegível — a ausência da chave em `Item.p` é o que codifica `E_i`.
_REFERENCIA_TEMPOS: dict[str, dict[str, float | None]] = {
    "CA1": {"L1": None, "L2": None, "L3": None, "L4": 39.0},
    "CA2": {"L1": None, "L2": None, "L3": None, "L4": 48.0},
    "TX3": {"L1": 20.0, "L2": 23.0, "L3": 25.0, "L4": 28.0},
    "TX4": {"L1": 16.0, "L2": 18.0, "L3": 20.0, "L4": 22.0},
    "TX5": {"L1": 24.0, "L2": 28.0, "L3": 30.0, "L4": 34.0},
    "TX6": {"L1": 18.0, "L2": 21.0, "L3": 22.0, "L4": 25.0},
    "TX7": {"L1": 22.0, "L2": 25.0, "L3": 27.0, "L4": 31.0},
    "TX8": {"L1": 26.0, "L2": 30.0, "L3": 32.0, "L4": 36.0},
}

#: Prazos, pesos e clientes da instância de referência: ``id -> (d, w, cliente)``.
#: Os clientes são rótulos fixos — os valores de ``d`` e ``w`` são os do enunciado
#: e não podem mudar, sob pena de o ótimo deixar de ser 144,0. A atribuição
#: respeita a regra do catálogo: cada cliente tem uma única criticidade, então
#: pedidos do mesmo cliente têm o mesmo peso. Fábio Assunção (peso 2) é o único
#: com dois pedidos, CA2 e TX7 — e o ótimo atrasa os dois, justamente por serem
#: baratos.
_REFERENCIA_PRAZOS_E_PESOS: dict[str, tuple[float, float, str]] = {
    "CA1": (45.0, 8.0, "Adriana Prado"),
    "CA2": (95.0, 2.0, "Fábio Assunção"),
    "TX3": (40.0, 5.0, "Camila Fontes"),
    "TX4": (30.0, 3.0, "Eduarda Nogueira"),
    "TX5": (50.0, 1.0, "Gabriela Munhoz"),
    "TX6": (35.0, 6.0, "Mariana Yamamoto"),
    "TX7": (55.0, 2.0, "Fábio Assunção"),
    "TX8": (42.0, 4.0, "Diego Vasconcelos"),
}

#: Ótimo da instância de referência, verificado por enumeração exaustiva.
OTIMO_REFERENCIA = 144.0


def instancia_referencia() -> Instancia:
    """Instância de 8 itens e 4 linhas usada como teste de regressão.

    Reproduz exatamente a tabela documentada no README e no relatório. O ótimo
    é ``Z = 144,0``, com ``L1: TX4→TX3``, ``L2: TX6→TX7``, ``L3: TX8→TX5`` e
    ``L4: CA1→CA2``.

    O detalhe que interessa: o ótimo deixa TX5 atrasar 25 u.t. porque seu peso é
    1, e protege TX6 (peso 6) e TX4 (peso 3). Uma implementação que "espalhe" o
    atraso igualmente entre os itens está minimizando a coisa errada.
    """
    itens: dict[str, Item] = {}
    for item_id, tempos in _REFERENCIA_TEMPOS.items():
        prazo, peso, cliente = _REFERENCIA_PRAZOS_E_PESOS[item_id]
        itens[item_id] = Item(
            id=item_id,
            p={linha: t for linha, t in tempos.items() if t is not None},
            d=prazo,
            w=peso,
            cabo_aco=familia(item_id) == PREFIXO_CABO_ACO,
            cliente=cliente,
        )
    inst = Instancia(
        itens=itens,
        linhas=list(LINHAS_PADRAO),
        setup=montar_setup(list(itens)),
    )
    inst.validar()
    return inst
