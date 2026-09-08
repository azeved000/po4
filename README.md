# RubberTech — programação da produção por PLI

## 1. O que é

Programação da produção de uma fábrica de correias transportadoras com **4
linhas paralelas não idênticas**. Cada item tem prazo, cliente e tempo de
processamento que depende da linha; itens com cabo de aço só rodam na linha
dedicada; e o tempo de preparação entre dois itens depende da ordem em que eles
são produzidos. O objetivo é minimizar o **atraso total ponderado**, `Σ w_i·T_i`,
em que o peso combina multa contratual e criticidade do cliente.

A solução é obtida por **Programação Linear Inteira Mista (PLI)** — programação
matemática exata, não heurística. As regras de despacho de `baselines.py` (EDD,
SPT, WSPT) existem **apenas** como coluna de comparação no relatório; nenhuma
delas é chamada pelo modelo, pelo solver ou pelo programa principal.

---

## 2. O modelo

Classificação de três campos: **`R_m | s_ij, M_i | Σ w_i T_i`** (GRAHAM et al.,
1979) — máquinas paralelas não relacionadas, setup dependente da sequência,
elegibilidade restrita de máquinas, atraso total ponderado.

### Conjuntos

| Símbolo | Significado |
|---|---|
| `J` | itens da carteira |
| `J0 = J ∪ {0}` | itens mais o nó fictício `0` de início de linha |
| `M` | linhas de produção |
| `E_i ⊆ M` | linhas elegíveis do item `i` |

### Parâmetros

| Símbolo | Significado |
|---|---|
| `p[i,k]` | tempo de processamento do item `i` na linha `k` (definido só para `k ∈ E_i`) |
| `s[i,j]` | setup para produzir `j` imediatamente após `i`; `s[0,j]` é o setup inicial da linha |
| `d[i]` | prazo de entrega |
| `w[i]` | peso do atraso |
| `α[i]` | penalidade de antecipação (0 por padrão) |
| `V` | big-M |
| `n` | número de itens |

### Variáveis

| Símbolo | Tipo | Significado |
|---|---|---|
| `x[i,k]` | binária | item `i` é produzido na linha `k` (existe só para `k ∈ E_i`) |
| `y[i,j,k]` | binária | `j` é produzido imediatamente após `i` na linha `k` |
| `C[i]` | contínua ≥ 0 | instante de conclusão |
| `T[i]` | contínua ≥ 0 | atraso |
| `A[i]` | contínua ≥ 0 | antecipação |
| `u[i]` | contínua ∈ [1, n] | posição na sequência (auxiliar MTZ) |

### Função objetivo

```
min Σ_{i∈J} ( w[i]·T[i] + α[i]·A[i] )
```

### Restrições

```
(1)   Σ_{k∈E_i} x[i,k] = 1                                 ∀ i∈J
(2)   Σ_{i∈J0, i≠j} y[i,j,k] = x[j,k]                      ∀ j∈J, k∈E_j
(2')  Σ_{j∈J, j≠i} y[i,j,k] ≤ x[i,k]                       ∀ i∈J, k∈E_i
(3)   Σ_{j∈J} y[0,j,k] ≤ 1                                 ∀ k∈M
(4)   C[j] ≥ s[0,j] + p[j,k] − V·(1 − y[0,j,k])            ∀ j∈J, k∈E_j
(4')  C[j] ≥ C[i] + s[i,j] + p[j,k] − V·(1 − y[i,j,k])     ∀ (i,j,k) arcos, i≠0
(5)   T[i] ≥ C[i] − d[i]                                   ∀ i∈J
(5')  A[i] ≥ d[i] − C[i]                                   ∀ i∈J
(6)   u[i] − u[j] + n·y[i,j,k] ≤ n − 1                     ∀ (i,j,k) arcos, i≠0
```

### Correspondência entre formulação e código

Os nomes da coluna da direita são os nomes reais das restrições no PuLP: eles
aparecem assim no arquivo `.lp` exportado.

| Elemento da formulação | Onde está no código |
|---|---|
| Conjunto `J` | `dominio.Instancia.J` |
| Conjunto `J0` | `dominio.Instancia.J0` |
| Conjunto `M` | `dominio.Instancia.M` |
| Conjunto `E_i` | `dominio.Instancia.elegiveis(i)` — são as chaves de `Item.p` |
| Arcos `(i,j,k)` válidos | `dominio.Instancia.arcos()` |
| Parâmetro `p[i,k]` | `dominio.Instancia.p(i, k)` |
| Parâmetro `s[i,j]` | `dominio.Instancia.s(i, j)` |
| Parâmetros `d[i]`, `w[i]` | `dominio.Item.d`, `dominio.Item.w` |
| Parâmetro `α[i]` | `modelo.ConfigModelo.penalidade_antecipacao` |
| Parâmetro `V` | `dominio.Instancia.big_m()` |
| Variável `x[i,k]` | `modelo.construir`, dicionário `x`; variável PuLP `x_{i}_{k}` |
| Variável `y[i,j,k]` | `modelo.construir`, dicionário `y`; variável PuLP `y_{i}_{j}_{k}` |
| Variável `C[i]` | `modelo.construir`, dicionário `C`; variável PuLP `C_{i}` |
| Variável `T[i]` | `modelo.construir`, dicionário `T`; variável PuLP `T_{i}` |
| Variável `A[i]` | `modelo.construir`, dicionário `A`; variável PuLP `A_{i}` |
| Variável `u[i]` | `modelo.construir`, dicionário `u`; variável PuLP `u_{i}` |
| Função objetivo | `modelo.py`, objetivo nomeado `atraso_ponderado_total` |
| Restrição (1) alocação única | `modelo.py`, restrição `alocacao_{i}` |
| Restrição (2) predecessor único | `modelo.py`, restrição `entrada_{j}_{k}` |
| Restrição (2') sucessor único | `modelo.py`, restrição `saida_{i}_{k}` |
| Restrição (3) uma cadeia por linha | `modelo.py`, restrição `origem_{k}` |
| Restrição (4) datação do primeiro item | `modelo.py`, restrição `tempo_inicial_{j}_{k}` |
| Restrição (4') datação dos demais | `modelo.py`, restrição `tempo_{i}_{j}_{k}` |
| Restrição (5) atraso | `modelo.py`, restrição `atraso_{i}` |
| Restrição (5') antecipação | `modelo.py`, restrição `antecipacao_{i}` |
| Restrição (6) MTZ | `modelo.py`, restrição `mtz_{i}_{j}_{k}` |

### Três notas de modelagem

**Big-M calculado, não arbitrado.** O valor usado é

```
V = Σ_i ( max_{k∈E_i} p[i,k] + max_{a≠i} s[a,i] ) + max_i d[i]
```

(implementado em `dominio.Instancia.big_m()`; vale 464,0 na instância de
referência). A primeira parcela limita superiormente a conclusão de qualquer
item — todos em série, sempre com o pior tempo e o pior setup de entrada — e a
segunda cobre o termo `−d[i]` das restrições de atraso. Um `V` arbitrariamente
grande (10⁶, por exemplo) manteria o modelo correto, mas na relaxação linear um
`y` fracionário compraria a desativação das restrições (4) e (4') quase de
graça: o limite inferior desabaria e o *branch-and-bound* perderia a régua que
usa para podar.

**Elegibilidade tratada no domínio das variáveis.** Variáveis para linhas
inelegíveis não são criadas — não são criadas e fixadas em zero, simplesmente
não existem. Na instância de referência isso significa 26 variáveis `x` em vez
de 32 e 172 variáveis `y` em vez de 256: **90 variáveis a menos, 31,2% da grade
cheia**. Na instância de 80 itens, 260 `x` e 17.200 `y` em vez de 320 e 25.600 —
**8.460 variáveis a menos, 32,6%**. Como consequência, o modelo não precisa que
o pré-processamento do solver descubra a elegibilidade, e nenhuma solução
inviável por elegibilidade é sequer representável.

**Eliminação de subciclos.** As restrições (4') já impedem subciclos: percorrer
um ciclo `i → j → … → i` exigiria `C[i] ≥ C[i] + (setups e processamentos
positivos)`, ou seja, `C[i] > C[i]`. As restrições (6) de Miller, Tucker e
Zemlin (1960) são portanto **redundantes** e entram só para fortalecer a
relaxação linear. Ligam e desligam pela flag `modelo.ConfigModelo.usar_mtz`
(padrão `True`) ou pelo argumento `--sem-mtz` na linha de comando. O efeito
medido está na seção 8.

---

## 3. Arquitetura

```
rubbertech/
├── README.md
├── requirements.txt
├── pyproject.toml               # metadados e configuração do pytest
├── src/rubbertech/
│   ├── dominio.py               # Item, Instancia, Tarefa, Programacao; validação e big-M
│   ├── instancias.py            # geradores determinísticos por estágio + instância de referência
│   ├── io_dados.py              # leitura e escrita de instâncias em JSON
│   ├── modelo.py                # construção do MILP em PuLP
│   ├── solver.py                # execução, status, gap, limite inferior
│   ├── solucao.py               # avaliador independente e extração da solução do solver
│   ├── validacao.py             # verificador de viabilidade e enumeração exaustiva
│   ├── baselines.py             # regras de despacho — SÓ para comparação
│   ├── relatorio.py             # saída textual formatada
│   └── visual.py                # gráfico de Gantt
├── scripts/
│   ├── resolver.py              # CLI principal
│   ├── validar_estagios.py      # estágios 1 a 4 contra a força bruta
│   └── experimentos.py          # baterias de escala, MTZ e comparação
├── data/instancias/             # instâncias em JSON
├── resultados/                  # relatórios, gráficos e CSVs gerados
└── tests/                       # testes automatizados (pytest)
```

**Regra de dependência.** `dominio.py` não importa nada do projeto. `modelo.py`
importa só `dominio`. `solucao.py` e `validacao.py` importam `dominio` (e o
`solucao`, no caso do `validacao`), nunca o modelo nem o solver. `solver.py`
importa `modelo`. Os scripts orquestram. Nenhum módulo de `src/` escreve na tela
fora de `relatorio.py` e `visual.py`. A consequência prática: cada peça pode ser
testada isolada, e nenhuma delas pode "concordar" com outra por compartilhar
código.

**Por que existe um avaliador independente.** `solucao.avaliar` recebe apenas a
ordem dos itens em cada linha — uma lista de nomes — e recalcula do zero setups,
instantes de início e fim, atrasos e valor do objetivo. Não olha nenhuma
variável do solver, não conhece o modelo e não importa o PuLP. É ele que diz
quanto custa uma programação. O solver, portanto, não confirma a si mesmo: seu
resultado é traduzido em sequências por `solucao.extrair` e reavaliado por
`solucao.avaliar`, e a diferença entre os dois valores aparece no relatório
(linha `conferência`). Se o modelo tivesse setup trocado, big-M curto ou erro de
sinal, os dois números divergiriam.

---

## 4. Como instalar e rodar

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

O solver CBC vem junto com o PuLP; não há nada mais para instalar. Não é preciso
instalar o pacote — os scripts acrescentam `src/` ao caminho de busca sozinhos.

### Exemplo 1 — resolver a instância de referência

```bash
python scripts/resolver.py --instancia referencia
```

```
====================================================================================
INSTÂNCIA
------------------------------------------------------------------------------------
itens ............... 8 (2 com cabo de aço)
linhas .............. 4: L1, L2, L3, L4
arcos válidos ....... 172
big-M calculado ..... 464,00
====================================================================================

====================================================================================
RESULTADO DA RESOLUÇÃO
====================================================================================
status .............. Optimal  (ótimo provado (o solver fechou o gap))
objetivo ............ 144,00
limite inferior ..... 144,00
gap ................. 0,00%
tempo ............... 13,47 s
tamanho do modelo ... 230 variáveis, 398 restrições
mensagem do solver .. Optimal solution found
conferência ......... objetivo recalculado de forma independente difere em 0,000000
====================================================================================

====================================================================================
PROGRAMAÇÃO DA PRODUÇÃO
====================================================================================

Linha L1: TX4 -> TX8
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  TX4          8,0      8,0     24,0     30,0   3,0      0,0  no prazo
 2  TX8          5,0     29,0     55,0     42,0   4,0     13,0  ATRASO

Linha L2: TX6 -> TX7
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  TX6          8,0      8,0     29,0     35,0   6,0      0,0  no prazo
 2  TX7          5,0     34,0     59,0     55,0   2,0      4,0  ATRASO

Linha L3: TX3 -> TX5
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  TX3          8,0      8,0     33,0     40,0   5,0      0,0  no prazo
 2  TX5          5,0     38,0     68,0     50,0   1,0     18,0  ATRASO

Linha L4: CA1 -> CA2
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  CA1         12,0     12,0     51,0     45,0   8,0      6,0  ATRASO
 2  CA2          5,0     56,0    104,0     95,0   2,0      9,0  ATRASO

====================================================================================
INDICADORES
------------------------------------------------------------------------------------
atraso ponderado (objetivo) . 144,00
atraso total (sem pesos) .... 50,00
itens atrasados ............. 5 de 8
makespan .................... 104,00
tempo total de setup ........ 56,00
ocupação por linha .......... L1=52,9%  L2=56,7%  L3=65,4%  L4=100,0%
====================================================================================

VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada.
```

Esta programação custa 144,0, o mesmo valor da programação documentada na seção
7. A instância tem ótimos alternativos: qual deles o CBC devolve depende da
ordem de exploração da árvore, mas o valor é o mesmo.

### Exemplo 2 — com gráfico de Gantt e arquivo de saída

```bash
python scripts/resolver.py --instancia estagio_4 --tempo-limite 60 --gantt resultados/gantt_estagio4.png --saida resultados/estagio4.txt
```

Últimas linhas da saída:

```
====================================================================================
INDICADORES
------------------------------------------------------------------------------------
atraso ponderado (objetivo) . 149,90
atraso total (sem pesos) .... 78,50
itens atrasados ............. 5 de 6
makespan .................... 65,10
tempo total de setup ........ 43,00
ocupação por linha .......... L1=84,0%  L2=97,2%  L3=100,0%
====================================================================================

VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada.

Relatório salvo em: resultados\estagio4.txt
Gráfico de Gantt salvo em: resultados/gantt_estagio4.png
```

No Gantt, cada item aparece como duas faixas — o setup (translúcido) e o
processamento (sólido) —, o prazo é a linha pontilhada vertical e os itens
atrasados levam borda e hachura.

Aqui também há ótimos alternativos: o valor 149,90 se repete a cada execução,
mas o makespan e o tempo total de setup podem variar, porque programações
diferentes custam o mesmo atraso ponderado.

### Exemplo 3 — validação dos estágios

```bash
python scripts/validar_estagios.py
```

```
========================================================================================
VALIDAÇÃO INCREMENTAL (n = 5, MTZ = sim)
========================================================================================
estágio    o que valida                          PLI  força bruta  tempo s  resultado
----------------------------------------------------------------------------------------
estágio 1  uma linha, setup zero               85.00        85.00     0.31  PASSOU
estágio 2  uma linha, setup assimétrico       179.40       179.40     0.28  PASSOU
estágio 3  armadilha de subciclo              850.80       850.80     0.56  PASSOU
estágio 4  elegibilidade restrita             401.80       401.80     1.44  PASSOU
----------------------------------------------------------------------------------------
Todos os estágios passaram: o modelo reproduz o ótimo exato.
========================================================================================
```

---

## 5. Como fornecer os próprios dados

Há duas formas: um arquivo JSON com os dados reais, ou os geradores
paramétricos.

### a) Arquivo JSON

Exemplo mínimo completo e funcional — 3 itens, 2 linhas, um item com cabo de aço
que só roda em `L2`. Está em `data/instancias/exemplo_minimo.json`:

```json
{
  "nome": "exemplo-minimo",
  "no_inicial": "INI",
  "linhas": ["L1", "L2"],
  "itens": [
    { "id": "TX1", "p": { "L1": 20, "L2": 24 }, "d": 30, "w": 5, "cabo_aco": false },
    { "id": "TX2", "p": { "L1": 15, "L2": 18 }, "d": 25, "w": 2, "cabo_aco": false },
    { "id": "CA1", "p": { "L2": 30 }, "d": 40, "w": 8, "cabo_aco": true }
  ],
  "setup": {
    "INI": { "TX1": 8, "TX2": 8, "CA1": 12 },
    "TX1": { "TX2": 5, "CA1": 20 },
    "TX2": { "TX1": 5, "CA1": 20 },
    "CA1": { "TX1": 11, "TX2": 11 }
  }
}
```

#### Campos

| Campo | Tipo | Obrigatório | Significado | Unidade |
|---|---|---|---|---|
| `nome` | texto | não | rótulo da instância, só para identificação | — |
| `no_inicial` | texto | não (padrão `"INI"`) | rótulo do nó fictício de início de linha; não pode coincidir com o id de um item | — |
| `linhas` | lista de textos | **sim** | nomes das linhas de produção | — |
| `itens` | lista de objetos | **sim** | a carteira de pedidos | — |
| `itens[].id` | texto | **sim** | identificador único do item | — |
| `itens[].p` | objeto `linha → número` | **sim** | tempo de processamento por linha **elegível** | tempo |
| `itens[].d` | número ≥ 0 | **sim** | prazo de entrega, contado a partir de zero | tempo |
| `itens[].w` | número ≥ 0 | **sim** | peso do atraso (multa × criticidade do cliente) | adimensional |
| `itens[].cabo_aco` | booleano | não (padrão `false`) | marca a família do item; usado no relatório e no Gantt | — |
| `setup` | objeto `anterior → { seguinte: número }` | **sim** | tempo de preparação entre dois itens consecutivos | tempo |

#### Cinco pontos que costumam gerar dúvida

1. **`p` só precisa conter as linhas elegíveis.** A ausência de uma linha em `p`
   é a forma de declarar que o item não roda ali. No exemplo, `CA1` só tem
   `"L2"`, e é assim que a elegibilidade restrita entra no modelo — nenhuma
   variável é criada para `CA1` fora de `L2`.
2. **A chave do setup é o par ordenado (anterior, seguinte).**
   `setup["TX1"]["CA1"]` é o tempo para produzir `CA1` logo depois de `TX1`.
3. **A matriz de setup não precisa ser simétrica, e não deve ser.** No exemplo,
   `TX1 → CA1` custa 20 (montar o dispositivo de tração dos cabos) e
   `CA1 → TX1` custa 11 (desmontar e limpar). É essa assimetria que dá a cada
   linha a estrutura de um caixeiro viajante assimétrico.
4. **O setup inicial de cada linha é a entrada cujo anterior é o nó fictício.**
   `setup["INI"]["CA1"] = 12` significa: se `CA1` for o primeiro item de uma
   linha, a linha gasta 12 antes de começar. O valor não depende da linha.
5. **Unidades.** O tempo é livre (minutos, horas, turnos), desde que o mesmo em
   `p`, `setup` e `d`. O peso `w` é adimensional e só a **proporção** entre os
   pesos importa: dobrar todos os pesos não muda a programação ótima.

#### Rodando o exemplo

```bash
python scripts/resolver.py --instancia data/instancias/exemplo_minimo.json
```

```
====================================================================================
INSTÂNCIA
------------------------------------------------------------------------------------
itens ............... 3 (1 com cabo de aço)
linhas .............. 2: L1, L2
arcos válidos ....... 13
big-M calculado ..... 154,00
====================================================================================

====================================================================================
RESULTADO DA RESOLUÇÃO
====================================================================================
status .............. Optimal  (ótimo provado (o solver fechou o gap))
objetivo ............ 62,00
limite inferior ..... 62,00
gap ................. 0,00%
tempo ............... 0,05 s
tamanho do modelo ... 30 variáveis, 42 restrições
mensagem do solver .. Optimal solution found
conferência ......... objetivo recalculado de forma independente difere em 0,000000
====================================================================================

====================================================================================
PROGRAMAÇÃO DA PRODUÇÃO
====================================================================================

Linha L1: TX1 -> TX2
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  TX1          8,0      8,0     28,0     30,0   5,0      0,0  no prazo
 2  TX2          5,0     33,0     48,0     25,0   2,0     23,0  ATRASO

Linha L2: CA1
------------------------------------------------------------------------------------
 #  item       setup   início      fim    prazo  peso   atraso  situação
------------------------------------------------------------------------------------
 1  CA1         12,0     12,0     42,0     40,0   8,0      2,0  ATRASO

====================================================================================
INDICADORES
------------------------------------------------------------------------------------
atraso ponderado (objetivo) . 62,00
atraso total (sem pesos) .... 25,00
itens atrasados ............. 2 de 3
makespan .................... 48,00
tempo total de setup ........ 25,00
ocupação por linha .......... L1=100,0%  L2=87,5%
====================================================================================

VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada.
```

Para partir de uma instância existente em vez de digitar tudo, gere o JSON de um
dos geradores e edite o arquivo:

```bash
python scripts/resolver.py --instancia estagio_4 --tempo-limite 10 --salvar-json data/instancias/minha.json
```

```
Instância salva em: data\instancias\minha.json
```

### b) Geradores paramétricos

| Gerador | Nome no CLI | O que gera | O que valida |
|---|---|---|---|
| `estagio_1_maquina_unica(n, seed)` | `estagio_1` | 1 linha, setup zero | o solver acha o ótimo trivial; a datação não inventa atraso |
| `estagio_2_setup(n, seed)` | `estagio_2` | 1 linha, setup assimétrico entre famílias | timing do setup e efeito da assimetria |
| `estagio_3_subciclos(n, seed)` | `estagio_3` | 1 linha, setup inicial caro e trocas de graça | eliminação de subciclos (restrições de tempo e MTZ) |
| `estagio_4_elegibilidade(n, m, frac_cabo, seed)` | `estagio_4` | várias linhas, parte da carteira presa à linha dedicada | a elegibilidade é respeitada; a linha dedicada vira gargalo |
| `estagio_5_intermediario(seed, n)` | `estagio_5` | ~20 itens, 4 linhas | desempenho do solver acima da força bruta |
| `estagio_6_completo(seed, n)` | `estagio_6` | ~80 itens, 4 linhas, ~1/4 com cabo de aço | o problema real |
| `instancia_referencia()` | `referencia` | 8 itens, 4 linhas, dados fixos | regressão: ótimo conhecido `Z = 144,0` |

```bash
python scripts/resolver.py --instancia estagio_5 --tempo-limite 120
python scripts/resolver.py --instancia estagio_6 --tempo-limite 300
```

Os parâmetros que valem a pena mexer estão em constantes nomeadas no topo de
`src/rubbertech/instancias.py`:

| Parâmetro | Constante / argumento | Padrão | Efeito |
|---|---|---|---|
| número de itens | argumento `n` | varia por estágio | tamanho do problema |
| número de linhas | argumento `m` (estágio 4) / `LINHAS_PADRAO` | 4 | paralelismo disponível |
| fração com cabo de aço | argumento `frac_cabo` / `FRACAO_CABO_ACO_PADRAO` | 0,25 | pressão sobre a linha dedicada |
| folga média dos prazos | `FOLGA_PRAZO_MEDIA` | 0,45 | prazo médio como fração do horizonte; menor = carteira mais atrasada |
| amplitude dos prazos | `FOLGA_PRAZO_DISPERSAO` | 0,70 | dispersão dos prazos em torno da média |
| distribuição dos pesos | `PESOS_POSSIVEIS`, `PESOS_PROBABILIDADES` | 1 a 8 | desigualdade entre clientes |
| velocidade das linhas | `FATOR_VELOCIDADE` | 1,00 a 1,40 | o quanto as máquinas são não idênticas |
| setups por família | `SETUP_INTRAFAMILIA`, `SETUP_TEXTIL_PARA_CABO`, `SETUP_CABO_PARA_TEXTIL`, `SETUP_INICIAL_*` | 5 / 20 / 11 / 8 e 12 | custo e assimetria da troca |
| reprodutibilidade | argumento `seed` | varia por estágio | mesma `seed` ⇒ instância idêntica |

Como os geradores são funções Python comuns, dá para montar uma instância nova
em três linhas e salvá-la em JSON:

```python
from rubbertech.instancias import estagio_6_completo
from rubbertech.io_dados import salvar

salvar(estagio_6_completo(seed=42, n=60), "data/instancias/carteira60.json")
```

### Erros comuns na entrada

`Instancia.validar()` roda antes de qualquer construção de modelo e recusa:

- instância sem itens ou sem linhas; linhas repetidas;
- nó fictício com o mesmo nome de um item;
- item sem nenhuma linha elegível (`p` vazio);
- `p` declarado para uma linha que não existe em `linhas`;
- tempo de processamento ausente, nulo, negativo ou não finito;
- prazo `d` negativo; peso `w` negativo;
- setup ausente para um par de itens que pode ficar consecutivo;
- setup negativo ou não finito.

As mensagens sempre dizem **qual** item ou par está errado. Dois casos reais:

```bash
python scripts/resolver.py --instancia erro_sem_linha.json
```

```
Instância inválida em 'erro_sem_linha.json': Item 'TX1' não possui nenhuma linha elegível.
```

```bash
python scripts/resolver.py --instancia erro_sem_setup.json
```

```
Instância inválida em 'erro_sem_setup.json': Setup ausente para o par ('TX2', 'CA1'), necessário porque existe arco válido entre esses itens.
```

Nos dois casos o programa termina com código de saída 1 e não chama o solver.

---

## 6. Como ler a saída

Tomando o bloco de resultado do exemplo 1:

```
status .............. Optimal  (ótimo provado (o solver fechou o gap))
objetivo ............ 144,00
limite inferior ..... 144,00
gap ................. 0,00%
tempo ............... 13,47 s
tamanho do modelo ... 230 variáveis, 398 restrições
mensagem do solver .. Optimal solution found
conferência ......... objetivo recalculado de forma independente difere em 0,000000
```

| Campo | Como ler |
|---|---|
| `status` | `Optimal` = ótimo provado. `Not Solved` = o solver parou no limite de tempo com uma solução viável. `Infeasible` = nenhuma programação satisfaz as restrições. `Undefined` = não houve solução utilizável. |
| `objetivo` | valor de `Σ w_i·T_i` (mais `Σ α_i·A_i`, se `--alfa > 0`) da melhor solução encontrada. |
| `limite inferior` | melhor limitante inferior provado pelo *branch-and-bound*. Com `Optimal`, é igual ao objetivo. |
| `gap` | distância relativa entre o objetivo e o limite inferior, na convenção do CBC: `(objetivo − limite inferior) / limite inferior`. Zero significa otimalidade provada; valores acima de 100% são normais quando o limite inferior ainda está fraco. |
| `tempo` | tempo de parede, incluindo a construção do modelo. |
| `tamanho do modelo` | número de variáveis e de restrições efetivamente geradas. |
| `conferência` | diferença entre o objetivo do solver e o objetivo recalculado do zero pelo avaliador independente. Deve ser 0. |

**`status = Not Solved` com objetivo preenchido não é solução ótima.** É uma
solução viável encontrada dentro do limite de tempo — um limitante superior. O
ótimo está entre o limite inferior e o objetivo, e o `gap` diz o tamanho dessa
faixa. Nesse caso o relatório imprime, logo abaixo:

```
ATENÇÃO: o valor acima é um limitante superior. O ótimo está entre o
limite inferior e o objetivo; o gap mede essa distância.
```

Para aumentar o tempo disponível, use `--tempo-limite` (em segundos).

Na tabela de programação, cada linha de item se lê assim:

```
 #  item       setup   início      fim    prazo  peso   atraso  situação
 2  TX8          5,0     29,0     55,0     42,0   4,0     13,0  ATRASO
```

- `#` — posição do item na sequência da linha;
- `setup` — preparação paga **antes** deste item, correspondente ao par
  (item anterior, este item); para o primeiro da linha, é o setup inicial;
- `início` e `fim` — janela de processamento, já **depois** do setup; portanto
  o setup ocupa a linha de `início − setup` até `início`;
- `prazo` — `d_i`; `peso` — `w_i`;
- `atraso` — `T_i = max(0, fim − prazo)`;
- `situação` — `ATRASO` quando `T_i > 0`, `no prazo` caso contrário.

No exemplo: `TX8` é o segundo item de `L1`, paga 5 de setup (das 24,0 às 29,0),
processa das 29,0 às 55,0, tinha prazo 42,0 e atrasa 13,0, com peso 4 —
contribuindo com 52,0 para o objetivo.

O bloco `INDICADORES` traz o atraso ponderado (o objetivo), o atraso total sem
pesos, quantos itens atrasaram, o makespan, o tempo total gasto em preparação e
a ocupação de cada linha (fração do makespan em que a linha esteve processando
ou em setup).

A última linha é o resultado do verificador independente. Qualquer coisa
diferente de `nenhuma violação encontrada` indica defeito no modelo ou na
extração da solução, e o programa termina com código 1.

---

## 7. Validação

A correção não é assumida; é verificada em três camadas independentes.

1. **Verificador independente** (`validacao.verificar`) — confere que cada item
   aparece exatamente uma vez, em linha elegível, sem sobreposição temporal, com
   os setups correspondentes aos pares consecutivos reais, e recalcula o
   objetivo (tolerância `1e-6`).
2. **Enumeração exaustiva** (`validacao.forca_bruta`) — para `n ≤ 8`, percorre
   todas as atribuições item→linha e todas as permutações dentro de cada linha e
   devolve o ótimo verdadeiro, sem solver nenhum; é a régua contra a qual o
   modelo é medido.
3. **Testes automatizados** (`pytest`) — incluindo o de regressão da instância de
   referência e o que compara o ótimo com e sem MTZ.

### A instância de referência

8 itens e 4 linhas. `CA1` e `CA2` têm cabo de aço e só rodam em `L4`.

| item | L1 | L2 | L3 | L4 | `d` | `w` |
|---|---|---|---|---|---|---|
| CA1 | — | — | — | 39 | 45 | 8 |
| CA2 | — | — | — | 48 | 95 | 2 |
| TX3 | 20 | 23 | 25 | 28 | 40 | 5 |
| TX4 | 16 | 18 | 20 | 22 | 30 | 3 |
| TX5 | 24 | 28 | 30 | 34 | 50 | 1 |
| TX6 | 18 | 21 | 22 | 25 | 35 | 6 |
| TX7 | 22 | 25 | 27 | 31 | 55 | 2 |
| TX8 | 26 | 30 | 32 | 36 | 42 | 4 |

Setups: inicial 12 para itens CA e 8 para TX; 5 dentro da mesma família; 20 de
TX para CA (montar o dispositivo de tração dos cabos) e 11 de CA para TX
(desmontar e limpar).

**Ótimo verificado por enumeração exaustiva: `Z = 144,0`**, com a programação

```
L1: TX4 -> TX3
L2: TX6 -> TX7
L3: TX8 -> TX5
L4: CA1 -> CA2
```

O ponto que interessa: o ótimo deixa **`TX5` atrasar 25 u.t.** porque seu peso é
1, e **protege `TX6`** (peso 6) e `TX4` (peso 3), que terminam no prazo. Uma
programação que espalhasse o atraso igualmente entre os itens estaria
minimizando o atraso *total*, não o atraso *ponderado* — é o teste que separa
uma função objetivo correta de uma plausível.

### Rodando os testes

```bash
python -m pytest tests -q
```

```
........................................................................ [100%]
72 passed in 18.38s
```

Cobertura, por arquivo:

| Arquivo | O que garante |
|---|---|
| `test_dominio.py` | validação recusa instância sem linha elegível, sem `p`, sem setup, com `d` ou `w` negativo; `big_m` é positivo e domina qualquer conclusão possível |
| `test_solucao.py` | `avaliar` reproduz um caso calculado à mão no próprio teste, com os números escritos explicitamente |
| `test_validacao.py` | `verificar` detecta item duplicado, item ausente, linha inelegível, sobreposição, setup trocado e objetivo adulterado; `forca_bruta` bate com uma segunda enumeração escrita de forma diferente |
| `test_modelo.py` | contagem de variáveis e restrições bate com o número de arcos válidos; nenhuma variável para linha inelegível; restrições têm os nomes documentados |
| `test_io_dados.py` | ida e volta pelo JSON preserva a instância e o ótimo; erros de formato têm mensagem específica |
| `test_regressao.py` | a instância de referência vale exatamente 144,0 pela força bruta, pelo avaliador e pelo modelo; o modelo bate com a força bruta em quatro instâncias pequenas com seeds fixas |
| `test_mtz.py` | o ótimo é o mesmo com e sem MTZ (o MTZ não pode cortar solução ótima) e a relaxação linear com MTZ não é pior |

---

## 8. Limitações e escala

**Crescimento do modelo.** O número de variáveis `y[i,j,k]` cresce com `n²·m`.
Medido:

| instância | itens | `x` | `y` | variáveis | restrições (com MTZ) |
|---|---|---|---|---|---|
| referência | 8 | 26 | 172 | 230 | 398 |
| completa | 80 | 260 | 17.200 | PLACEHOLDER_VARS_80 | PLACEHOLDER_RESTR_80 |

PLACEHOLDER_ESCALA

**Estocagem limitada.** A área de estocagem não é modelada como capacidade
explícita; ela é tratada indiretamente pela penalidade de antecipação `α`, que
empurra a produção para perto do prazo (regime just-in-time). **A penalidade
está desligada por padrão** (`α = 0`, objetivo de atraso ponderado puro) e se
liga com `--alfa`, ou por item via `ConfigModelo.penalidade_antecipacao`.

**Outras limitações.** Não há preempção, nem datas de liberação, nem
indisponibilidade programada de linha; o setup é sequenciado na própria linha e
não consome recurso compartilhado; e os tempos são determinísticos.

---

## 9. Referências

ALLAHVERDI, A. The third comprehensive survey on scheduling problems with setup
times/costs. **European Journal of Operational Research**, v. 246, n. 2,
p. 345-378, 2015.

ARENALES, M.; ARMENTANO, V.; MORABITO, R.; YANASSE, H. **Pesquisa Operacional:
para cursos de engenharia**. 2. ed. Rio de Janeiro: Elsevier, 2015.

GRAHAM, R. L.; LAWLER, E. L.; LENSTRA, J. K.; RINNOOY KAN, A. H. G. Optimization
and approximation in deterministic sequencing and scheduling: a survey.
**Annals of Discrete Mathematics**, v. 5, p. 287-326, 1979.

MILLER, C. E.; TUCKER, A. W.; ZEMLIN, R. A. Integer programming formulation of
traveling salesman problems. **Journal of the ACM**, v. 7, n. 4, p. 326-329,
1960.

PINEDO, M. L. **Scheduling: theory, algorithms, and systems**. 5. ed. Cham:
Springer, 2016.
