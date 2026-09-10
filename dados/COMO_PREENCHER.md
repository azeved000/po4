# Como preencher um arquivo de instância

Guia para quem tem os dados da fábrica e precisa montar o JSON de entrada **à
mão**, sem ler código. Como JSON não aceita comentário, este arquivo é o lugar
onde a explicação mora.

A mesma tabela abaixo (e mais nada além dela — é a mesma fonte) aparece em
`python main.py legenda --entrada`. Se as duas um dia divergirem, este arquivo
e a saída do comando é que estão desatualizados; a fonte de verdade é
`rubbertech/relatorio.py::CAMPOS_ENTRADA`.

---

## 1. Campos

| Campo | Símbolo | O que significa | Unidade | Obrigatório | Exemplo |
|---|---|---|---|---|---|
| `nome` | — | rótulo da instância; só identificação, não entra no modelo | — | não (padrão `"instancia"`) | `"referencia"` |
| `no_inicial` | `0` (nó fictício) | rótulo do nó fictício de início de linha; não pode coincidir com o id de um item | — | não (padrão `"INI"`) | `"INI"` |
| `linhas` | `M` | nomes das linhas de produção | — | **sim** | `["L1", "L2"]` |
| `itens[].id` | `i ∈ J` | identificador único do item | — | **sim** | `"TX1"` |
| `itens[].p` | `p[i,k]` | tempo de processamento por linha **elegível**; a ausência de uma linha diz "este item não roda ali" | tempo (livre) | **sim** | `{"L1": 20, "L2": 24}` |
| `itens[].d` | `d[i]` | prazo de entrega, contado a partir de zero | tempo (= unidade de `p`) | **sim** | `30` |
| `itens[].w` | `w[i]` | peso do atraso (multa contratual × criticidade do cliente) | adimensional | **sim** | `5` |
| `itens[].cabo_aco` | — | rótulo de família para relatório e Gantt; **não** restringe elegibilidade | — | não (padrão `false`) | `true` |
| `setup` | `s[i,j]` | tempo de preparação para produzir `j` logo após `i`; indexado por par ordenado `(anterior, seguinte)` | tempo (= unidade de `p` e `d`) | **sim** | `{"INI": {"TX1": 8}, "TX1": {"TX2": 5}}` |

Cinco pontos que costumam causar erro:

1. **`p` só lista as linhas elegíveis.** É a omissão de uma linha dentro de `p`
   que impede o item de ser produzido nela — não existe uma lista separada de
   restrições em outro lugar do arquivo. O campo `cabo_aco` é **apenas** rótulo
   para os relatórios e o Gantt; ele não restringe nada.
2. **`setup` é indexado por par ordenado `(item anterior, item seguinte)`**, e
   não precisa ser simétrico: `setup["TX1"]["CA1"]` pode (e costuma) diferir de
   `setup["CA1"]["TX1"]`. É essa assimetria que representa montar contra
   desmontar o dispositivo de tração dos cabos.
3. **A chave `"INI"`** (ou o valor de `no_inicial`, se você mudou o padrão)
   guarda o setup **inicial** de cada linha, aplicado ao primeiro item
   produzido nela.
4. **Unidades de tempo são livres**, desde que consistentes entre `p`, `setup`
   e `d`. Se `p` está em horas, `d` precisa estar em horas — misturar unidades
   não dá erro de validação, só um resultado sem sentido.
5. **`w` é adimensional** e só a proporção entre os pesos importa: dobrar todos
   os pesos dobra o objetivo sem mudar a programação ótima.

---

## 2. Exemplo completo (3 itens, 2 linhas)

Pronto para copiar e adaptar. `TX1` e `TX2` rodam em qualquer uma das duas
linhas; `CA1` (cabo de aço) só roda em `L2`.

```json
{
  "nome": "exemplo-3-itens",
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

Repare que `setup` só precisa dos pares que o modelo de fato pode usar — para
3 itens e a elegibilidade acima, isso é todo par `(anterior, seguinte)` em que
`seguinte` está em `E_seguinte` e `anterior` é `"INI"` ou está na mesma linha.
Se um par ficar de fora e for necessário, a validação recusa e nomeia
exatamente o par que falta (caso 2 abaixo). Este mesmo arquivo existe pronto
em `dados/exemplo_minimo.json`.

---

## 3. Erros comuns

A validação (`rubbertech.dados.Instancia.validar`) recusa dados impossíveis
com uma mensagem que **nomeia o item ou o par responsável** — nunca um
`KeyError` cru. As três mensagens abaixo são reais: cada caso foi montado como
um JSON à parte, rodado com `python main.py resolver --instancia <arquivo>` e
a mensagem foi colada daqui, sem edição.

### a) Item sem linha elegível

Entrada (`itens[].p` vazio — `TX2` não lista nenhuma linha):

```json
{ "id": "TX2", "p": {}, "d": 25, "w": 2 }
```

Mensagem:

```
Instância inválida em 'dados\instancia_sem_linha.json': Item 'TX2' não possui nenhuma linha elegível.
```

### b) Setup faltando

Entrada (o par `("TX2", "TX1")` nunca é declarado em `setup`, mas `TX1` e
`TX2` rodam na mesma linha e um pode suceder o outro):

```json
"setup": {
  "INI": { "TX1": 8, "TX2": 8 },
  "TX1": { "TX2": 5 }
}
```

Mensagem:

```
Instância inválida em 'dados\instancia_setup_faltando.json': Setup ausente para o par ('TX2', 'TX1'), necessário porque existe arco válido entre esses itens.
```

### c) Prazo negativo

Entrada:

```json
{ "id": "TX1", "p": { "L1": 20, "L2": 24 }, "d": -5, "w": 5 }
```

Mensagem:

```
Instância inválida em 'dados\instancia_prazo_negativo.json': Item 'TX1' tem prazo negativo: d = -5.0.
```

---

## 4. Referências

- Tabela de saída (o que significa cada indicador do relatório):
  `python main.py legenda --saida`.
- Formulação matemática completa (`p[i,k]`, `s[i,j]`, restrições): seção 2 do
  [README](../README.md).
