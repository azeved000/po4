"""Testes essenciais do projeto RubberTech.

Rodar com ``python -m pytest testes.py -q`` (menos de 60 s no total).

O critério para um teste estar aqui é ser capaz de acusar um erro que nada mais
acusaria. Em ordem de importância:

1. a instância de referência vale **exatamente 144,0** por três caminhos
   independentes — força bruta, avaliador e modelo PLI;
2. o avaliador reproduz um caso calculado à mão, com os números escritos no
   próprio teste (se ele fosse gerado por outra função do projeto, um erro
   comum aos dois passaria despercebido);
3. o verificador acusa programação adulterada;
4. a validação recusa dados impossíveis nomeando o item ou o par culpado;
5. o modelo bate com a enumeração exaustiva, com e sem MTZ.
"""

from __future__ import annotations

import pytest

from rubbertech import dados
from rubbertech.conferencia import avaliar, conferir, edd, forca_bruta, verificar
from rubbertech.dados import (
    OTIMO_REFERENCIA,
    PROGRAMACAO_REFERENCIA,
    Instancia,
    InstanciaInvalida,
    Item,
    Programacao,
    Tarefa,
    instancia_referencia,
)
from rubbertech.modelo import ConfigModelo, construir, resolver, tamanho


def instancia_manual() -> Instancia:
    """Três itens, duas linhas; B só roda em L1 e C só em L2."""
    itens = {
        "A": Item(id="A", p={"L1": 10.0, "L2": 12.0}, d=20.0, w=2.0),
        "B": Item(id="B", p={"L1": 8.0}, d=15.0, w=3.0),
        "C": Item(id="C", p={"L2": 6.0}, d=9.0, w=1.0),
    }
    setup = {
        ("INI", "A"): 3.0, ("INI", "B"): 5.0, ("INI", "C"): 4.0,
        ("A", "B"): 7.0, ("B", "A"): 2.0, ("A", "C"): 6.0, ("C", "A"): 1.0,
    }
    inst = Instancia(itens=itens, linhas=["L1", "L2"], setup=setup)
    inst.validar()
    return inst


#: Instâncias pequenas (n ≤ 8) com seeds fixas, cobrindo os quatro estágios.
CASOS_PEQUENOS = [
    ("sem_setup", dados.gerar(4, m=1, frac_cabo=0.0, com_setup=False, seed=11)),
    ("setup_assimetrico", dados.gerar(4, m=1, frac_cabo=0.4, seed=12)),
    (
        "armadilha_subciclo",
        dados.gerar(4, m=1, frac_cabo=0.4, seed=13, armadilha_subciclo=40.0),
    ),
    ("elegibilidade", dados.gerar(5, m=3, frac_cabo=0.4, seed=14)),
]


# ======================================================================
# 1. Validação dos dados de entrada
# ======================================================================
def test_validacao_recusa_item_sem_linha_elegivel() -> None:
    """A mensagem tem que nomear o item — senão sobra inspecionar 80 na mão."""
    inst = instancia_manual()
    inst.itens["D"] = Item(id="D", p={}, d=10.0, w=1.0)
    with pytest.raises(InstanciaInvalida, match="'D'.*linha elegível"):
        inst.validar()


def test_validacao_recusa_setup_ausente_nomeando_o_par() -> None:
    inst = instancia_manual()
    del inst.setup[("A", "B")]
    with pytest.raises(InstanciaInvalida, match=r"Setup ausente.*'A'.*'B'"):
        inst.validar()


def test_big_m_sai_dos_dados_e_domina_a_pior_conclusao() -> None:
    """V = Σ_i (max_k p[i,k] + max_a s[a,i]) + max_i d[i], não um número redondo.

    Para a instância manual: (12+3) + (8+7) + (6+6) + 20 = 62.
    """
    inst = instancia_manual()
    assert inst.big_m() == pytest.approx(62.0)
    assert inst.big_m() >= max(item.d for item in inst.itens.values())


# ======================================================================
# 2. Avaliador independente
# ======================================================================
def test_avaliar_reproduz_calculo_manual() -> None:
    """L1: A -> B, L2: C. Contas feitas à mão, aqui no teste.

    L1: setup INI->A = 3  => início 3,  fim 3 + 10 = 13, d = 20 => T = 0
        setup A->B   = 7  => início 20, fim 20 + 8 = 28, d = 15 => T = 13, w = 3
    L2: setup INI->C = 4  => início 4,  fim 4 + 6 = 10,  d = 9  => T = 1,  w = 1
    Objetivo = 3*13 + 1*1 = 40
    """
    prog = avaliar(instancia_manual(), {"L1": ["A", "B"], "L2": ["C"]})
    assert (prog.tarefa("A").setup, prog.tarefa("A").fim) == (3.0, 13.0)
    assert (prog.tarefa("B").setup, prog.tarefa("B").fim, prog.tarefa("B").atraso) == (
        7.0,
        28.0,
        13.0,
    )
    assert (prog.tarefa("C").fim, prog.tarefa("C").atraso) == (10.0, 1.0)
    assert prog.objetivo == pytest.approx(40.0)


def test_avaliar_usa_o_setup_assimetrico_correto() -> None:
    """Invertendo a ordem em L1, o setup é s[B,A] = 2, não s[A,B] = 7.

    setup INI->B = 5 => fim 5 + 8 = 13, d = 15 => T = 0
    setup B->A   = 2 => início 15, fim 15 + 10 = 25, d = 20 => T = 5, w = 2 => 10
    """
    prog = avaliar(instancia_manual(), {"L1": ["B", "A"]})
    assert prog.tarefa("A").setup == 2.0
    assert prog.tarefa("A").fim == pytest.approx(25.0)
    assert prog.objetivo == pytest.approx(10.0)


def test_avaliar_recusa_linha_inelegivel() -> None:
    with pytest.raises(InstanciaInvalida, match="não é elegível"):
        avaliar(instancia_manual(), {"L2": ["B"]})


# ======================================================================
# 3. Verificador
# ======================================================================
def test_verificador_aceita_programacao_sa() -> None:
    inst = instancia_manual()
    assert verificar(inst, avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})) == []


def test_verificador_detecta_item_duplicado_e_ausente() -> None:
    """A aparece em duas linhas e B em nenhuma."""
    inst = instancia_manual()
    violacoes = verificar(inst, avaliar(inst, {"L1": ["A"], "L2": ["A", "C"]}))
    assert any("'A' aparece 2 vezes" in v for v in violacoes)
    assert any("'B' não aparece" in v for v in violacoes)


def test_verificador_detecta_linha_inelegivel() -> None:
    """`avaliar` recusaria isso, então a programação é montada à mão."""
    inst = instancia_manual()
    prog = Programacao(
        sequencias={"L1": ["A", "C"], "L2": ["B"]},
        tarefas=[
            Tarefa(item="A", linha="L1", inicio=3.0, fim=13.0, setup=3.0, atraso=0.0),
            Tarefa(item="C", linha="L1", inicio=19.0, fim=25.0, setup=6.0, atraso=16.0),
            Tarefa(item="B", linha="L2", inicio=5.0, fim=13.0, setup=5.0, atraso=0.0),
        ],
        objetivo=16.0,
    )
    assert any("'B' foi alocado à linha 'L2'" in v for v in verificar(inst, prog))


def test_verificador_detecta_objetivo_adulterado() -> None:
    inst = instancia_manual()
    prog = avaliar(inst, {"L1": ["A", "B"], "L2": ["C"]})
    prog.objetivo = 1.0
    violacoes = verificar(inst, prog)
    assert len(violacoes) == 1 and "difere do recalculado" in violacoes[0]


# ======================================================================
# 4. Estrutura do modelo
# ======================================================================
def test_nenhuma_variavel_para_linha_inelegivel() -> None:
    """Elegibilidade no **domínio** das variáveis: elas não chegam a existir."""
    inst = instancia_referencia()
    prob, var = construir(inst)

    for i, k in var.x:
        assert k in inst.elegiveis(i)
    for i, j, k in var.y:
        assert k in inst.elegiveis(j)
        assert i == inst.no_inicial or k in inst.elegiveis(i)
    # Concretamente: nada de CA1 ou CA2 fora da L4.
    assert not [(i, k) for (i, k) in var.x if i.startswith("CA") and k != "L4"]
    assert not [
        (i, j, k) for (i, j, k) in var.y if k != "L4" and "CA" in (i[:2], j[:2])
    ]
    # Números concretos: 2 itens presos à L4 + 6 livres em 4 linhas = 26 pares.
    assert len(var.x) == 26
    assert len(var.y) == sum(1 for _ in inst.arcos()) == 172
    assert tamanho(prob) == (230, 398)


def test_restricoes_tem_os_nomes_da_formulacao() -> None:
    """Os nomes PuLP batem com a numeração do relatório; sem eles o .lp
    exportado vira _C1, _C2... e depurar vira adivinhação."""
    nomes = set(construir(instancia_referencia())[0].constraints)
    for esperado in (
        "alocacao_CA1", "entrada_TX3_L2", "saida_TX3_L2", "origem_L4",
        "tempo_inicial_CA1_L4", "tempo_TX3_TX4_L1", "atraso_TX5",
        "antecipacao_TX5", "mtz_TX3_TX4_L1",
    ):
        assert esperado in nomes
    assert all(not nome.startswith("_C") for nome in nomes)


def test_sem_mtz_nao_cria_variaveis_u() -> None:
    inst = dados.gerar(5, m=3, frac_cabo=0.4, seed=14)
    _, var = construir(inst, ConfigModelo(usar_mtz=False))
    assert var.u == {}


# ======================================================================
# 5. Entrada e saída em JSON
# ======================================================================
def test_ida_e_volta_pelo_json_preserva_a_instancia(tmp_path) -> None:
    original = instancia_referencia()
    recarregada = dados.carregar(
        dados.salvar(original, tmp_path / "ref.json", nome="referencia")
    )

    assert recarregada.linhas == original.linhas
    assert recarregada.no_inicial == original.no_inicial
    assert recarregada.setup == original.setup
    assert list(recarregada.itens) == list(original.itens)
    for item_id, item in original.itens.items():
        copia = recarregada.itens[item_id]
        assert (copia.p, copia.d, copia.w, copia.cabo_aco) == (
            item.p, item.d, item.w, item.cabo_aco,
        )
    # O que realmente importa: o ótimo não muda depois de passar pelo disco.
    assert forca_bruta(recarregada)[0] == pytest.approx(OTIMO_REFERENCIA)


def test_json_preserva_a_assimetria_do_setup() -> None:
    """s[TX3,CA1] = 20 (montar o dispositivo) e s[CA1,TX3] = 11 (desmontar)."""
    estrutura = dados.para_dicionario(instancia_referencia())
    assert estrutura["setup"]["TX3"]["CA1"] == 20.0
    assert estrutura["setup"]["CA1"]["TX3"] == 11.0
    assert estrutura["setup"]["INI"]["CA1"] == 12.0


# ======================================================================
# 6. Regressão: a instância de referência vale exatamente 144,0
# ======================================================================
def test_referencia_vale_144_pela_forca_bruta_e_pelo_avaliador() -> None:
    """Dois caminhos que não passam por solver nenhum."""
    inst = instancia_referencia()

    custo, prog_bruta = forca_bruta(inst)
    assert custo == pytest.approx(OTIMO_REFERENCIA)
    assert verificar(inst, prog_bruta) == []

    prog = avaliar(inst, PROGRAMACAO_REFERENCIA)
    assert prog.objetivo == pytest.approx(OTIMO_REFERENCIA)
    assert verificar(inst, prog) == []
    # O ótimo sacrifica TX5 (peso 1) e protege TX6 (peso 6) e TX4 (peso 3).
    # Uma implementação que espalhasse o atraso minimizaria a coisa errada.
    assert prog.tarefa("TX5").atraso == pytest.approx(25.0)
    assert prog.tarefa("TX6").atraso == pytest.approx(0.0)
    assert prog.tarefa("TX4").atraso == pytest.approx(0.0)


def test_referencia_vale_144_pelo_modelo() -> None:
    """O terceiro caminho: o MILP, conferido pelo avaliador independente."""
    inst = instancia_referencia()
    res = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=300)

    assert res.status == "Optimal"
    assert res.objetivo == pytest.approx(OTIMO_REFERENCIA)
    assert res.sequencias is not None
    conf = conferir(inst, res.sequencias, res.objetivo)
    assert conf.programacao.objetivo == pytest.approx(OTIMO_REFERENCIA)
    assert conf.divergencia == pytest.approx(0.0, abs=1e-6)
    assert conf.violacoes == []
    # O item de peso 8 (CA1) tem que estar na única linha elegível.
    assert res.sequencias["L4"][0] == "CA1"


# ======================================================================
# 7. Modelo × força bruta, e MTZ ligado × desligado
# ======================================================================
@pytest.mark.parametrize("nome,inst", CASOS_PEQUENOS, ids=[c[0] for c in CASOS_PEQUENOS])
def test_modelo_bate_com_a_forca_bruta(nome: str, inst: Instancia) -> None:
    otimo_bruto, _ = forca_bruta(inst)
    res = resolver(inst, tempo_limite=120)
    assert res.status == "Optimal", f"{nome}: {res.mensagem}"
    assert res.objetivo == pytest.approx(otimo_bruto, abs=1e-4)
    assert res.sequencias is not None
    conf = conferir(inst, res.sequencias, res.objetivo)
    assert conf.programacao.objetivo == pytest.approx(otimo_bruto, abs=1e-4)
    assert conf.violacoes == []
    # Todos os itens sequenciados: a armadilha do estágio 3 fecharia um
    # subciclo, e `extrair_sequencias` teria levantado erro antes de chegar aqui.
    assert sorted(i for seq in res.sequencias.values() for i in seq) == sorted(inst.J)


@pytest.mark.parametrize("nome,inst", CASOS_PEQUENOS, ids=[c[0] for c in CASOS_PEQUENOS])
def test_otimo_identico_com_e_sem_mtz(nome: str, inst: Instancia) -> None:
    """As restrições (6) são redundantes: (4') já impede subciclos, porque um
    ciclo implicaria C[i] > C[i]. Um erro de sinal nelas não deixaria o modelo
    inviável — ele continuaria "Optimal", só que com um valor pior."""
    com = resolver(inst, ConfigModelo(usar_mtz=True), tempo_limite=120)
    sem = resolver(inst, ConfigModelo(usar_mtz=False), tempo_limite=120)
    otimo_bruto, _ = forca_bruta(inst)

    assert com.status == sem.status == "Optimal", f"{nome}"
    assert com.objetivo == pytest.approx(sem.objetivo, abs=1e-4)
    assert com.objetivo == pytest.approx(otimo_bruto, abs=1e-4)


# ======================================================================
# 8. EDD — só comparação
# ======================================================================
def test_edd_produz_programacao_valida_e_nunca_melhor_que_o_otimo() -> None:
    """O EDD não é o método de solução; só precisa ser uma régua honesta."""
    inst = instancia_referencia()
    prog = edd(inst)
    assert verificar(inst, prog) == []
    assert prog.objetivo >= OTIMO_REFERENCIA - 1e-9
