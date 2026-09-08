"""Entidades e invariantes do problema de programação da produção.

Este módulo é a base da arquitetura: ele não importa nada do restante do
projeto. A razão é prática — o avaliador independente (`solucao.avaliar`), o
verificador (`validacao.verificar`) e o modelo PLI (`modelo.construir`) precisam
partir exatamente da mesma descrição do problema. Se o domínio dependesse do
modelo, um erro de modelagem se propagaria silenciosamente para a validação e
não haveria como detectá-lo.

Notação de três campos (Graham et al., 1979): ``R_m | s_ij, M_i | Σ w_i T_i``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass


class InstanciaInvalida(ValueError):
    """Erro de consistência dos dados de entrada.

    Levantado por :meth:`Instancia.validar`. As mensagens sempre nomeiam o item
    ou o par responsável, porque um "instância inválida" genérico obrigaria a
    inspecionar 80 itens na mão.
    """


@dataclass(frozen=True)
class Item:
    """Um item da carteira de pedidos (uma correia a produzir).

    O tempo de processamento é um dicionário ``linha -> tempo`` e não um vetor
    denso: as chaves presentes *definem* o conjunto de linhas elegíveis do item
    (``E_i``). Essa escolha é o que permite ao modelo não criar variáveis para
    pares (item, linha) impossíveis, o que é mais forte do que criá-las e
    fixá-las em zero.

    Atributos:
        id: identificador curto e único (ex.: ``"TX3"``, ``"CA1"``).
        p: tempo de processamento por linha elegível, ``p[k] = p[i,k]``.
        d: prazo de entrega (``d_i``).
        w: peso do atraso, combinando multa contratual e criticidade do cliente.
        cabo_aco: marca itens com cabo de aço. É informativo/documental — a
            restrição de elegibilidade propriamente dita vive nas chaves de ``p``.
    """

    id: str
    p: dict[str, float]
    d: float
    w: float
    cabo_aco: bool = False

    @property
    def linhas_elegiveis(self) -> tuple[str, ...]:
        """Conjunto ``E_i``, na ordem em que foi declarado (determinismo)."""
        return tuple(self.p)

    def tempo(self, linha: str) -> float:
        """``p[i,k]``, com erro explícito quando a linha não é elegível."""
        if linha not in self.p:
            raise InstanciaInvalida(
                f"Item '{self.id}' não é elegível para a linha '{linha}' "
                f"(elegíveis: {list(self.p)})."
            )
        return self.p[linha]

    def __hash__(self) -> int:
        """Hash pelo id.

        A geração automática falharia porque ``p`` é um dicionário (não
        hasheável), e o id já é único dentro de uma instância.
        """
        return hash(self.id)


@dataclass
class Instancia:
    """Uma instância completa do problema ``R_m | s_ij, M_i | Σ w_i T_i``.

    Atributos:
        itens: mapa ``id -> Item``. A ordem de inserção define a ordem de ``J``.
        linhas: linhas de produção disponíveis (``M``).
        setup: ``setup[(i, j)]`` = tempo de preparação para produzir ``j``
            imediatamente depois de ``i``. A matriz é **assimétrica**
            (``s[i,j] != s[j,i]``), o que dá a cada linha a estrutura de um
            Problema do Caixeiro Viajante assimétrico. Quando ``i`` é o nó
            fictício (:attr:`no_inicial`), o valor é o setup inicial da linha.
        no_inicial: rótulo do nó fictício de início de linha (o "0" da
            formulação). É um atributo, e não a constante ``"0"``, para nunca
            colidir com o id de um item real.
    """

    itens: dict[str, Item]
    linhas: list[str]
    setup: dict[tuple[str, str], float]
    no_inicial: str = "INI"

    # ------------------------------------------------------------------
    # Conjuntos da formulação
    # ------------------------------------------------------------------
    @property
    def J(self) -> list[str]:
        """Conjunto ``J`` dos itens."""
        return list(self.itens)

    @property
    def J0(self) -> list[str]:
        """Conjunto ``J0 = J ∪ {0}``, com o nó fictício na frente."""
        return [self.no_inicial, *self.itens]

    @property
    def M(self) -> list[str]:
        """Conjunto ``M`` das linhas."""
        return list(self.linhas)

    @property
    def n(self) -> int:
        """Número de itens (``n = |J|``), usado no big-M das restrições MTZ."""
        return len(self.itens)

    def elegiveis(self, i: str) -> tuple[str, ...]:
        """Conjunto ``E_i`` de linhas elegíveis do item ``i``."""
        return self.itens[i].linhas_elegiveis

    def p(self, i: str, k: str) -> float:
        """``p[i,k]``."""
        return self.itens[i].tempo(k)

    def s(self, i: str, j: str) -> float:
        """``s[i,j]``, com erro explícito quando o par não foi definido."""
        try:
            return self.setup[(i, j)]
        except KeyError:
            raise InstanciaInvalida(
                f"Setup ausente para o par ('{i}', '{j}')."
            ) from None

    # ------------------------------------------------------------------
    # Estrutura do grafo de sequenciamento
    # ------------------------------------------------------------------
    def arcos(self) -> Iterator[tuple[str, str, str]]:
        """Gera os trios ``(i, j, k)`` para os quais ``y[i,j,k]`` deve existir.

        Um arco é válido quando ``i != j``, a linha ``k`` é elegível para o
        sucessor ``j``, e o predecessor ``i`` ou é o nó fictício ou também é
        elegível para ``k``. Não gerar os demais é o principal redutor de
        tamanho do modelo: com cerca de 1/4 da carteira presa à Linha 4, a
        diferença em relação ao grafo completo é de várias vezes.
        """
        for j in self.itens:
            for k in self.elegiveis(j):
                for i in self.J0:
                    if i == j:
                        continue
                    if i == self.no_inicial or k in self.elegiveis(i):
                        yield (i, j, k)

    def pares_de_setup(self) -> set[tuple[str, str]]:
        """Pares ``(i, j)`` cujo setup é efetivamente necessário ao modelo."""
        return {(i, j) for i, j, _ in self.arcos()}

    def big_m(self) -> float:
        """Calcula ``V`` a partir da instância, em vez de arbitrar um número.

        Fórmula::

            V = Σ_i ( max_{k∈E_i} p[i,k] + max_{a≠i} s[a,i] ) + max_i d[i]

        A primeira parcela é um limitante superior para a conclusão do último
        item de qualquer linha (todos os itens em série, sempre com o pior tempo
        de processamento e o pior setup de entrada); a segunda cobre o termo
        ``- d[i]`` que aparece nas restrições de atraso.

        Por que não usar um número grande e redondo: com um ``V`` exagerado o
        modelo continua **correto**, mas a relaxação linear das restrições (4) e
        (4') fica frouxa — um ``y`` fracionário compra a desativação da
        restrição quase de graça — e o limite inferior do branch-and-bound
        desaba. Em instâncias de 80 itens isso é a diferença entre resolver e
        não resolver.
        """
        total = 0.0
        for i, item in self.itens.items():
            maior_p = max(item.p.values(), default=0.0)
            maior_s = max(
                (
                    valor
                    for (origem, destino), valor in self.setup.items()
                    if destino == i and origem != i
                ),
                default=0.0,
            )
            total += maior_p + maior_s
        maior_d = max((item.d for item in self.itens.values()), default=0.0)
        return total + maior_d

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------
    def validar(self) -> None:
        """Verifica as invariantes da instância; não retorna nada, ou levanta erro.

        Roda antes de qualquer construção de modelo: um setup faltando vira, no
        PuLP, um ``KeyError`` no meio de um laço de milhares de restrições, e a
        mensagem resultante não ajuda ninguém.
        """
        if not self.itens:
            raise InstanciaInvalida("A instância não possui itens.")
        if not self.linhas:
            raise InstanciaInvalida("A instância não possui linhas de produção.")
        if len(set(self.linhas)) != len(self.linhas):
            raise InstanciaInvalida(f"Há linhas repetidas em 'linhas': {self.linhas}.")
        if self.no_inicial in self.itens:
            raise InstanciaInvalida(
                f"O nó fictício '{self.no_inicial}' colide com o id de um item."
            )

        for chave, item in self.itens.items():
            if chave != item.id:
                raise InstanciaInvalida(
                    f"Chave '{chave}' do dicionário de itens não corresponde ao "
                    f"id '{item.id}'."
                )
            if not item.p:
                raise InstanciaInvalida(
                    f"Item '{item.id}' não possui nenhuma linha elegível."
                )
            for linha, tempo in item.p.items():
                if linha not in self.linhas:
                    raise InstanciaInvalida(
                        f"Item '{item.id}' declara tempo na linha '{linha}', que "
                        f"não existe na instância (linhas: {self.linhas})."
                    )
                if tempo is None or not math.isfinite(tempo) or tempo <= 0:
                    raise InstanciaInvalida(
                        f"Tempo de processamento inválido para o par "
                        f"('{item.id}', '{linha}'): {tempo!r}."
                    )
            if item.d < 0:
                raise InstanciaInvalida(
                    f"Item '{item.id}' tem prazo negativo: d = {item.d}."
                )
            if item.w < 0:
                raise InstanciaInvalida(
                    f"Item '{item.id}' tem peso negativo: w = {item.w}. Pesos "
                    "negativos invalidariam a linearização de T."
                )

        for i, j in sorted(self.pares_de_setup()):
            if (i, j) not in self.setup:
                raise InstanciaInvalida(
                    f"Setup ausente para o par ('{i}', '{j}'), necessário porque "
                    f"existe arco válido entre esses itens."
                )
            valor = self.setup[(i, j)]
            if valor is None or not math.isfinite(valor) or valor < 0:
                raise InstanciaInvalida(
                    f"Setup inválido para o par ('{i}', '{j}'): {valor!r}."
                )


@dataclass
class Tarefa:
    """Um item já alocado e datado dentro de uma programação.

    A janela ``[inicio, fim]`` cobre apenas o processamento; o ``setup`` que a
    precede é guardado à parte para que o relatório consiga mostrar quanto do
    horizonte foi consumido por preparação — o número que justifica modelar
    setup dependente da sequência.
    """

    item: str
    linha: str
    inicio: float
    fim: float
    setup: float
    atraso: float


@dataclass
class Programacao:
    """Uma solução completa: o que roda em cada linha, quando, e a que custo.

    Atributos:
        sequencias: ``linha -> lista ordenada de ids``.
        tarefas: as mesmas informações, já datadas (ordem irrelevante).
        objetivo: valor de ``Σ_i (w_i T_i + α_i A_i)`` recalculado.
    """

    sequencias: dict[str, list[str]]
    tarefas: list[Tarefa]
    objetivo: float

    def tarefa(self, item: str) -> Tarefa:
        """Acesso por item, para o verificador e o relatório."""
        for tarefa in self.tarefas:
            if tarefa.item == item:
                return tarefa
        raise KeyError(f"Item '{item}' não está na programação.")

    def tarefas_da_linha(self, linha: str) -> list[Tarefa]:
        """Tarefas de uma linha, ordenadas cronologicamente."""
        return sorted(
            (t for t in self.tarefas if t.linha == linha), key=lambda t: t.inicio
        )
