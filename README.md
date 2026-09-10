# RubberTech — programação da produção por PLI

## 1. O que é

Programação da produção de uma fábrica de correias transportadoras com **4
linhas paralelas não idênticas**. Cada item tem prazo, cliente e tempo de
processamento que depende da linha; itens com cabo de aço só rodam na linha
dedicada; e o tempo de preparação entre dois itens depende da ordem em que eles
são produzidos. O objetivo é minimizar o **atraso total ponderado**, `Σ w_i·T_i`,
em que o peso combina multa contratual e criticidade do cliente.

A solução é obtida por **Programação Linear Inteira Mista (PLI)** — programação
matemática exata, não heurística. A regra de despacho EDD (`conferencia.edd`)
existe **apenas** como coluna de comparação no relatório; ela não é chamada pelo
modelo, pelo solver nem pelo caminho de solução.

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
| Conjunto `J` | `dados.Instancia.J` |
| Conjunto `J0` | `dados.Instancia.J0` |
| Conjunto `M` | `dados.Instancia.M` |
| Conjunto `E_i` | `dados.Instancia.elegiveis(i)` — são as chaves de `Item.p` |
| Arcos `(i,j,k)` válidos | `dados.Instancia.arcos()` |
| Parâmetro `p[i,k]` | `dados.Instancia.p(i, k)` |
| Parâmetro `s[i,j]` | `dados.Instancia.s(i, j)` |
| Parâmetros `d[i]`, `w[i]` | `dados.Item.d`, `dados.Item.w` |
| Parâmetro `α[i]` | `modelo.ConfigModelo.penalidade_antecipacao` |
| Parâmetro `V` | `dados.Instancia.big_m()` |
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

(implementado em `dados.Instancia.big_m()`; vale 464,0 na instância de
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
po4/
├── README.md
├── requirements.txt
├── pyproject.toml          # metadados e configuração do pytest
├── main.py                 # ponto de entrada único: resolver | validar |
│                           # experimentos | legenda
├── rubbertech/
│   ├── __init__.py
│   ├── dados.py            # Item, Instancia, Tarefa, Programacao; validação,
│   │                       # big-M, gerador, instância de referência, JSON
│   ├── modelo.py           # construção do MILP em PuLP, execução, status e gap
│   ├── conferencia.py      # avaliador independente, verificador, força bruta, EDD
│   └── relatorio.py        # saída textual formatada, legenda e gráfico de Gantt
├── testes.py               # todos os testes (pytest)
├── dados/                  # instâncias em JSON
│   └── COMO_PREENCHER.md   # guia de preenchimento do JSON de entrada
└── resultados/             # relatórios, gráficos e CSVs gerados
```

**Regra de dependência.**

```
dados        -> (nada)
modelo       -> dados            [+ PuLP]
conferencia  -> dados            [sem PuLP, sem modelo]
relatorio    -> dados            [+ matplotlib]
main         -> todos
```

`conferencia.py` **não pode importar `modelo.py` nem o PuLP**. É essa proibição
que transforma o avaliador e a força bruta em segunda opinião de verdade, e não
em eco do solver. `dados.py` não importa nada do projeto, para que o modelo e a
conferência partam exatamente da mesma descrição do problema — se o domínio
dependesse do modelo, um erro de modelagem se propagaria para a verificação e
não haveria como detectá-lo.

**Por que existe um avaliador independente.** `conferencia.avaliar` recebe
apenas a ordem dos itens em cada linha — uma lista de nomes — e recalcula do
zero setups, instantes de início e fim, atrasos e valor do objetivo. Não olha
nenhuma variável do solver, não conhece o modelo e não importa o PuLP. É ele que
diz quanto custa uma programação.

O solver, portanto, não confirma a si mesmo. `modelo.resolver` devolve
**somente as sequências** (`linha → ordem dos itens`), extraídas das variáveis
`y` por `modelo.extrair_sequencias`; todo o resto do número volta a ser
calculado do lado de fora, por `conferencia.conferir`. A diferença entre o
objetivo do solver e o recalculado aparece no relatório na linha `conferência`.
Se o modelo tivesse setup trocado, big-M curto ou erro de sinal, os dois números
divergiriam.

---

## 4. Como instalar e rodar

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

O solver CBC vem junto com o PuLP; não há nada mais para instalar. Não é preciso
instalar o pacote: `main.py` e `testes.py` ficam na raiz, ao lado de
`rubbertech/`.

Os quatro subcomandos:

```bash
python main.py resolver --instancia referencia
python main.py validar
python main.py experimentos --experimento todos
python main.py legenda
```

`legenda` explica os campos de entrada e os indicadores de saída sem exigir
leitura de código — ver a seção 5 para o uso.

### Exemplo 1 — resolver a instância de referência

```bash
python main.py resolver --instancia referencia
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
tempo ............... 14,90 s
tamanho do modelo ... 230 variáveis, 398 restrições
mensagem do solver .. Optimal solution found
conferência ......... objetivo recalculado de forma independente difere em 0,000000
====================================================================================
```

seguido da programação linha a linha, do bloco `INDICADORES` e da linha
`VERIFICAÇÃO INDEPENDENTE: nenhuma violação encontrada.`

O ótimo vale **144,0**. Há mais de uma programação de custo 144 (trocar `TX3` e
`TX8` entre `L1` e `L3` dá o mesmo valor); a que o relatório documenta é a da
seção 7.

### Exemplo 2 — com gráfico de Gantt e arquivo de saída

```bash
python main.py resolver --instancia referencia --gantt resultados/gantt_referencia.png --saida resultados/referencia.txt
```

### Exemplo 3 — outras instâncias

```bash
python main.py resolver --instancia dados/exemplo_minimo.json
python main.py resolver --instancia gerar:20 --tempo-limite 60
python main.py resolver --instancia gerar:10:3:7 --sem-mtz
```

`gerar:n[:m[:seed]]` chama `dados.gerar` com `n` itens, `m` linhas e a semente
dada (padrões `m=4`, `seed=0`).

### Opções de `resolver`

| Opção | Padrão | O que faz |
|---|---|---|
| `--instancia` | `referencia` | arquivo JSON, `referencia` ou `gerar:n[:m[:seed]]` |
| `--tempo-limite` | `300` | limite de tempo do solver, em segundos |
| `--sem-mtz` | desligado | desliga as restrições (6), que são redundantes |
| `--alfa` | `0.0` | penalidade de antecipação `α`; 0 desliga |
| `--solver` | `CBC` | `CBC` ou `HiGHS` (este exige `pip install highspy`) |
| `--gantt` | — | salva o gráfico de Gantt no caminho dado |
| `--saida` | — | salva o relatório textual no caminho dado |
| `--salvar-json` | — | grava a instância usada em JSON |
| `--verboso` | desligado | mostra o log do solver |

O programa termina com código 0 quando há programação e nenhuma violação, e 1
caso contrário.

### Como alterar o limite de tempo do solver

Há duas formas, para dois usos diferentes.

**Por execução, pela linha de comando** — vale só para aquele comando. Nos três
subcomandos que resolvem alguma coisa, é `--tempo-limite`, em segundos:

```bash
python main.py resolver --instancia referencia --tempo-limite 600
python main.py validar --tempo-limite 60
python main.py experimentos --tempo-limite 300
```

**Mudando o padrão** — para não repetir a opção toda vez. Altere
`TEMPO_LIMITE_PADRAO` em [`rubbertech/modelo.py`](rubbertech/modelo.py) (valor
atual: `300`). O número é em **segundos** e passa a valer para os três
subcomandos (`resolver`, `validar` e `experimentos`) sempre que `--tempo-limite`
não for informado.

Três observações:

- **O limite é por resolução, não pelo comando inteiro.** Em `experimentos`,
  que resolve dezenas de instâncias, o tempo total é aproximadamente o limite
  multiplicado pelo número de resoluções que não convergirem antes.
- **Atingir o limite não é erro.** O programa devolve a melhor solução viável
  encontrada, sinalizada no `status` (`Not Solved`), e o `gap` indica quão
  longe do ótimo ela pode estar. O relatório destaca isso com um aviso.
- **Aumentar o limite ajuda em instâncias médias, mas não resolve a escala de
  80 itens.** Pelos experimentos da seção 8, nessa escala o limite inferior
  permanece em zero e o gap fica indefinido independentemente do tempo
  concedido — o gargalo não é tempo insuficiente, é o incumbente inicial ruim
  da formulação big-M nesse tamanho.

---

## 5. Como fornecer os próprios dados

### a) Arquivo JSON

O formato foi escolhido para ser escrito **à mão** por quem tem os dados da
fábrica, e não para ser compacto. `dados/exemplo_minimo.json` é o menor exemplo
completo.

```json
{
  "nome": "exemplo-minimo",
  "no_inicial": "INI",
  "linhas": ["L1", "L2"],
  "itens": [
    {"id": "TX1", "p": {"L1": 20, "L2": 24}, "d": 30, "w": 5, "cabo_aco": false},
    {"id": "TX2", "p": {"L1": 15, "L2": 18}, "d": 25, "w": 2, "cabo_aco": false},
    {"id": "CA1", "p": {"L2": 30}, "d": 40, "w": 8, "cabo_aco": true}
  ],
  "setup": {
    "INI": {"TX1": 8, "TX2": 8, "CA1": 12},
    "TX1": {"TX2": 5, "CA1": 20},
    "TX2": {"TX1": 5, "CA1": 20},
    "CA1": {"TX1": 11, "TX2": 11}
  }
}
```

O que cada campo significa, a unidade, se é obrigatório e os pontos que
costumam causar erro (elegibilidade em `p`, assimetria do `setup`, setup
inicial em `"INI"`, unidades livres mas consistentes, `w` adimensional) estão
documentados em **um lugar só**, para não haver duas versões da mesma
explicação a divergir com o tempo:

- `python main.py legenda --entrada` — a mesma tabela, formatada no terminal;
- [`dados/COMO_PREENCHER.md`](dados/COMO_PREENCHER.md) — a tabela por escrito,
  um exemplo completo de 3 itens prontos para copiar, e a mensagem real que a
  validação devolve para os erros mais comuns (item sem linha elegível, setup
  faltando, prazo negativo).

### b) Gerador paramétrico

Há **um** gerador determinístico, `dados.gerar`:

```python
gerar(n, m=4, frac_cabo=0.25, com_setup=True, seed=0, armadilha_subciclo=None)
```

| Argumento | Significado |
|---|---|
| `n` | número de itens |
| `m` | número de linhas; usa as `m` primeiras de `L1…L4`, e a última delas é a dedicada a cabo de aço |
| `frac_cabo` | fração da carteira presa à linha dedicada |
| `com_setup` | `False` zera toda a matriz de setup |
| `seed` | semente; o gerador é determinístico, para os experimentos serem reproduzíveis |
| `armadilha_subciclo` | quando dado, substitui a matriz de setup: entrar na linha custa esse valor e trocar de item é de graça |

Os quatro estágios da validação incremental são **combinações de argumentos**, e
não funções distintas:

| Estágio | Chamada | O que valida |
|---|---|---|
| 1 | `gerar(5, m=1, frac_cabo=0, com_setup=False)` | uma linha, sem setup: o solver acha o ótimo trivial e a datação por big-M não inventa atraso |
| 2 | `gerar(5, m=1, frac_cabo=0.4)` | uma linha, setup assimétrico: timing do setup e efeito de `s[i,j] ≠ s[j,i]` |
| 3 | `gerar(5, m=1, frac_cabo=0.4, armadilha_subciclo=40)` | armadilha de subciclo: só as restrições (4') seguram o modelo |
| 4 | `gerar(5, m=3, frac_cabo=0.4)` | elegibilidade restrita: nenhuma variável para par (item, linha) impossível; a linha dedicada vira gargalo |

`armadilha_subciclo` é o único parâmetro que sobreviveu à unificação dos
geradores, porque a estrutura de custos que ela cria — setup inicial punitivo e
trocas gratuitas — não é expressável pelas famílias de itens. Sem ela, um modelo
sem eliminação de subciclos acharia ótimo fechar um ciclo entre os itens e nunca
pagar o setup inicial: solução que existe no grafo, mas não no chão de fábrica.

A carteira real da fábrica é `gerar(80)` — 80 itens, 4 linhas, 25% com cabo de
aço.

---

## 6. Como ler a saída

A referência rápida destes indicadores também está disponível no terminal, com
`python main.py legenda --saida`.

```
status .............. Optimal  (ótimo provado (o solver fechou o gap))
objetivo ............ 144,00
limite inferior ..... 144,00
gap ................. 0,00%
tempo ............... 14,90 s
tamanho do modelo ... 230 variáveis, 398 restrições
mensagem do solver .. Optimal solution found
conferência ......... objetivo recalculado de forma independente difere em 0,000000
```

| Campo | Como ler |
|---|---|
| `status` | `Optimal` = ótimo provado. `Not Solved` = o solver parou no limite de tempo com uma solução viável. `Infeasible` = nenhuma programação satisfaz as restrições. `Undefined` = não houve solução utilizável. |
| `objetivo` | valor de `Σ w_i·T_i` (mais `Σ α_i·A_i`, se `--alfa > 0`) da melhor solução encontrada. |
| `limite inferior` | melhor limitante inferior provado pelo *branch-and-bound*. Com `Optimal`, é igual ao objetivo. |
| `gap` | distância relativa entre o objetivo e o limite inferior, na convenção do CBC: `(objetivo − limite inferior) / limite inferior`. Zero significa otimalidade provada; valores acima de 100% são normais quando o limite inferior ainda está fraco. Quando não dá para calcular (limite inferior 0 ou indisponível), a tela e o CSV escrevem `indefinido (...)` por extenso — nunca deixam a célula vazia ou mostram `-%`. |
| `tempo` | tempo de parede, incluindo a construção do modelo. |
| `tamanho do modelo` | número de variáveis e de restrições efetivamente geradas. |
| `conferência` | diferença entre o objetivo do solver e o objetivo recalculado do zero pelo avaliador independente. Deve ser 0. |

**Os tempos não são reprodutíveis entre máquinas — e não precisam ser.** `tempo`
depende do processador, da carga da máquina e da versão do CBC instalada; a
mesma instância pode levar 14 s numa máquina e 19 s noutra, sem que isso
signifique regressão nenhuma. O que se espera reproduzir ao rodar este projeto
é o **objetivo** e o **status** — inclusive `otimo_provado` — não a duração. Os
tempos impressos nos exemplos deste README e em `resultados/referencia.txt`
são de uma execução específica, só para dar a ordem de grandeza.

**Convenção de unidade do gap.** Na tela e **nos CSVs** o gap está sempre em
**porcentagem**: a coluna se chama `gap_percentual` e `80,0` quer dizer 80%.
Internamente `modelo.Resultado.gap` guarda a fração, e `Resultado.gap_percentual`
faz a conversão — um único ponto de verdade, para não haver tabela com fração de
um lado e porcentagem do outro.

**Convenção do gap indefinido.** Quando o limite inferior é 0 (ou indisponível),
o gap relativo não é definido — e isso **não é um erro de formatação**: é o
achado central da seção 8, o *branch-and-bound* não conseguiu provar nenhum
limitante além do trivial. Por isso nem a tela nem o CSV deixam a célula vazia
ou escrevem só um traço (`-%`, que lê como número que falhou a calcular): a
tela escreve `indefinido (limite inferior = 0)` (ou `indefinido (limite
inferior indisponível)`), e a coluna `gap_percentual` do CSV grava a palavra
`indefinido` por extenso. Célula vazia em CSV é ambígua com dado faltando; a
ausência de gap aqui é informação, não lacuna.

**`status = Not Solved` com objetivo preenchido não é solução ótima.** É uma
solução viável encontrada dentro do limite de tempo — um limitante superior. O
ótimo está entre o limite inferior e o objetivo, e o `gap` diz o tamanho dessa
faixa. Nesse caso o relatório imprime, destacado, o limite que foi atingido:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ATENÇÃO: atingiu o limite de 300 s: a solução abaixo é VIÁVEL, mas NÃO é
comprovadamente ótima. O ótimo verdadeiro está entre o limite inferior e o objetivo
mostrados acima; o gap mede essa distância. Para tentar fechar o gap, use
--tempo-limite com um valor maior (ver 'Como alterar o limite de tempo do solver' no
README).
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

O valor no aviso é o `--tempo-limite` efetivamente usado naquela execução, não
um número fixo. A quebra de linha é automática (`textwrap.fill`, na mesma
largura das réguas do relatório), então acompanha qualquer mudança futura
dessa largura sem precisar recortar a frase à mão. Ver "Como alterar o limite
de tempo do solver" na seção 4.

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

A correção não é assumida; é verificada em três camadas independentes, nenhuma
das quais passa pelo solver.

1. **Verificador independente** (`conferencia.verificar`) — confere que cada
   item aparece exatamente uma vez, em linha elegível, sem sobreposição
   temporal, com os setups correspondentes aos pares consecutivos reais, e
   recalcula o objetivo (tolerância `1e-6`).
2. **Enumeração exaustiva** (`conferencia.forca_bruta`) — para `n ≤ 8`, percorre
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

### Validação incremental

```bash
python main.py validar
```

```
========================================================================================
VALIDAÇÃO INCREMENTAL (n = 5, MTZ = sim)
========================================================================================
estágio    o que valida                          PLI  força bruta  tempo s  resultado
----------------------------------------------------------------------------------------
estágio 1  uma linha, sem setup                85.00        85.00     0.35  PASSOU
estágio 2  uma linha, setup assimétrico       179.40       179.40     0.32  PASSOU
estágio 3  armadilha de subciclo              850.80       850.80     0.41  PASSOU
estágio 4  elegibilidade restrita             223.30       223.30     0.37  PASSOU
----------------------------------------------------------------------------------------
Todos os estágios passaram: o modelo reproduz o ótimo exato.
========================================================================================
```

Cada estágio isola um aspecto do modelo numa instância pequena o bastante para a
força bruta (ver a tabela da seção 5b). Se o ótimo do solver não bater com o da
enumeração, não adianta olhar a instância de 80 itens.

### Rodando os testes

```bash
python -m pytest testes.py -q
```

```
..........................                                               [100%]
26 passed in 20.09s
```

São 20 funções de teste (26 casos, contando as parametrizadas). O critério para
um teste estar em `testes.py` é ser capaz de acusar um erro que nada mais
acusaria:

| Grupo | O que garante |
|---|---|
| validação | recusa item sem linha elegível e setup ausente, com mensagem que nomeia o item ou o par; `big_m` sai dos dados e domina a pior conclusão |
| avaliador | reproduz um caso calculado à mão, com os números escritos no próprio teste; aplica o setup assimétrico correto; recusa linha inelegível |
| verificador | detecta item duplicado, item ausente, linha inelegível e objetivo adulterado |
| modelo | nenhuma variável para linha inelegível; as restrições têm os nomes da formulação; `--sem-mtz` não cria as variáveis `u` |
| JSON | ida e volta preserva a instância **e o ótimo**; a assimetria do setup sobrevive |
| regressão | a instância de referência vale exatamente 144,0 pela força bruta, pelo avaliador e pelo modelo |
| MTZ e força bruta | o modelo bate com a enumeração em quatro instâncias pequenas com seeds fixas, e o ótimo é o mesmo com e sem MTZ |
| EDD | produz programação válida e nunca melhor que o ótimo |

---

## 8. Limitações e escala

Todos os experimentos desta seção usam **o mesmo limite de tempo, 120 s por
resolução** — o valor de `TEMPO_LIMITE_PADRAO` em vigor quando estes CSVs foram
gerados. Isso importa: com limites diferentes, o mesmo `n` apareceria com
objetivos diferentes em tabelas distintas, e a comparação não significaria
nada.

> **Nota de reprodutibilidade.** O padrão do projeto mudou para 300 s (ver
> "Como alterar o limite de tempo do solver", seção 4); os CSVs em
> `resultados/` **não** foram regravados com o novo padrão — refazê-los para
> `n = 80` a 300 s custaria horas de execução, e os números abaixo continuam
> válidos como estão, desde que lidos com o limite de 120 s que os gerou. Para
> reproduzir esta seção com o padrão atual, rode `python main.py experimentos
> --experimento todos` (usa 300 s automaticamente) ou passe `--tempo-limite 120`
> para comparar com os números exatos abaixo.

```bash
python main.py experimentos --experimento todos
```

Os CSVs vão para `resultados/` (`escala.csv`, `mtz.csv`, `edd.csv`). A coluna
de gap se chama `gap_percentual` e está **em porcentagem** nos três.

**Crescimento do modelo.** O número de variáveis `y[i,j,k]` cresce com `n²·m`.
Medido:

| instância | itens | `x` | `y` | variáveis | restrições (com MTZ) |
|---|---|---|---|---|---|
| referência | 8 | 26 | 172 | 230 | 398 |
| completa | 80 | 260 | 17.200 | 17.780 | 34.904 |

**Onde o CBC deixa de provar otimalidade.** `resultados/escala.csv`, semente 6:

| `n` | variáveis | restrições | status | objetivo | limite inferior | `gap_percentual` | tempo (s) |
|---|---|---|---|---|---|---|---|
| 6 | 126 | 208 | Optimal | 780,10 | 780,10 | 0,00 | 1,9 |
| 8 | 230 | 398 | Optimal | 620,00 | 620,00 | 0,00 | 22,9 |
| 10 | 366 | 652 | Not Solved | 935,30 | 166,66 | 461,00 | 120,0 |
| 20 | 1220 | 2279 | Not Solved | 4 537,40 | 0,00 | indefinido | 119,2 |
| 80 | 17780 | 34904 | Not Solved | 118 298,50 | 0,00 | indefinido | 87,4 |

**A fronteira é entre 8 e 10 itens.** Com 8 itens o ótimo é provado em 23 s; com
10 o solver esgota os 120 s com um limite inferior de 166,66 contra um
incumbente de 935,30. De 20 itens em diante o limite inferior nem sai de zero, e
o gap relativo deixa de ser definido (`indefinido` na coluna). O `objetivo`
dessas linhas é um **limitante superior**, não o ótimo.

O tempo de 87 s em `n = 80` não contradiz o limite de 120 s: nessa escala boa
parte do orçamento vai na construção e na escrita do modelo de 17 780 variáveis,
e o CBC encerra antes por seus próprios critérios.

**MTZ ligado × desligado.** `resultados/mtz.csv`, três sementes (6, 7, 8) por
tamanho, 30 resoluções. O que se reporta é **quantas execuções provaram
otimalidade** e o **tempo médio até a prova** — e não a média dos objetivos:
comparar incumbentes de execuções que não convergiram não permite conclusão,
porque cada uma parou num ponto diferente da árvore de busca.

| MTZ | provou ótimo | tempo médio até a prova |
|---|---|---|
| sim | 6 de 15 | 21,2 s |
| não | 6 de 15 | 20,3 s |

**As restrições (6) não pagaram o próprio custo nestas instâncias.** Provam
otimalidade nos mesmos 6 casos (`n = 6` e `n = 8`, todas as sementes) e com
tempo médio praticamente igual — 21,2 s contra 20,3 s, diferença dentro do
ruído. Em `n = 10` o efeito chega a ser adverso: com MTZ o limite inferior fica
em 166,66 (semente 6), contra 363,59 sem MTZ. As 258 restrições adicionais
encarecem cada relaxação linear mais do que estreitam o limitante.

Isso não invalida o argumento teórico — o MTZ *pode* fortalecer a relaxação —
mas mostra que, com este big-M e este solver, o ganho não aparece na faixa
testada. O padrão continua `usar_mtz=True` porque é a formulação descrita no
relatório; `--sem-mtz` permite reproduzir a coluna de comparação. O que os dois
lados **sempre** concordam é no ótimo, quando ele é provado: é o que
`testes.py::test_otimo_identico_com_e_sem_mtz` garante.

**Modelo exato × EDD.** `resultados/edd.csv`, três sementes por tamanho. O EDD
é apenas régua de comparação; não é o método de solução do trabalho.

| `n` | status do PLI | objetivo PLI (média) | objetivo EDD (média) | ganho médio do PLI¹ |
|---|---|---|---|---|
| 6 | Optimal (3/3) | 534,3 | 663,8 | +21,3% |
| 8 | Optimal (3/3) | 466,9 | 652,0 | +25,2% |
| 10 | Not Solved (0/3) | 870,4 | 916,0 | −5,1% |
| 20 | Not Solved (0/3) | 5 302,6 | 1 427,2 | −335,1% |
| 80 | Not Solved (0/3) | 109 976,8 | 5 085,3 | −2 809,3% |

¹ média dos ganhos calculados instância a instância, `(EDD − PLI) / EDD`, e
não o ganho entre as médias das duas colunas anteriores.

**O modelo exato só ganha do EDD onde consegue provar o ótimo.** Em `n ≤ 8` o
ganho é de 21% a 25% em média (chegando a 47% na semente 8 com `n = 8`), e vem
de agrupar itens da mesma família para economizar preparação — decisão que o EDD
não enxerga, porque ordena por prazo e despacha para a linha que termina antes.

Acima disso o resultado se inverte, e é preciso dizê-lo sem maquiagem: em 120 s
o incumbente do CBC é **pior** que o do EDD, e muito pior em `n = 80`. O
*branch-and-bound* gasta o orçamento provando limites em vez de melhorar a
solução, e a formulação big-M dá um incumbente inicial ruim. Para a carteira
completa, portanto, o modelo exato desta formulação **não** é utilizável no
limite de tempo adotado: ou se aumenta muito o tempo, ou se troca de solver
(HiGHS), ou se aceita a regra de despacho como ponto de partida. É a limitação
central do trabalho, e a seção 5 da conclusão do relatório precisa registrá-la.

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
