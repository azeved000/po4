"""Testes da entrada de dados em JSON — o caminho por onde entram dados reais."""

from __future__ import annotations

import json

import pytest

from rubbertech.dominio import InstanciaInvalida
from rubbertech.io_dados import carregar, de_dicionario, para_dicionario, salvar
from rubbertech.instancias import instancia_referencia
from rubbertech.validacao import forca_bruta

EXEMPLO_MINIMO = {
    "nome": "exemplo-minimo",
    "no_inicial": "INI",
    "linhas": ["L1", "L2"],
    "itens": [
        {"id": "TX1", "p": {"L1": 20, "L2": 24}, "d": 30, "w": 5, "cabo_aco": False},
        {"id": "TX2", "p": {"L1": 15, "L2": 18}, "d": 25, "w": 2, "cabo_aco": False},
        {"id": "CA1", "p": {"L2": 30}, "d": 40, "w": 8, "cabo_aco": True},
    ],
    "setup": {
        "INI": {"TX1": 8, "TX2": 8, "CA1": 12},
        "TX1": {"TX2": 5, "CA1": 20},
        "TX2": {"TX1": 5, "CA1": 20},
        "CA1": {"TX1": 11, "TX2": 11},
    },
}


def test_ida_e_volta_preserva_a_instancia(tmp_path) -> None:
    original = instancia_referencia()
    caminho = salvar(original, tmp_path / "ref.json", nome="referencia")
    recarregada = carregar(caminho)

    assert recarregada.linhas == original.linhas
    assert recarregada.no_inicial == original.no_inicial
    assert recarregada.setup == original.setup
    assert list(recarregada.itens) == list(original.itens)
    for item_id, item in original.itens.items():
        copia = recarregada.itens[item_id]
        assert (copia.p, copia.d, copia.w, copia.cabo_aco) == (
            item.p,
            item.d,
            item.w,
            item.cabo_aco,
        )
    # O que realmente importa: o ótimo não muda depois de passar pelo disco.
    assert forca_bruta(recarregada)[0] == pytest.approx(144.0)


def test_exemplo_minimo_do_readme_e_valido() -> None:
    """O exemplo documentado tem que carregar e ser resolvível."""
    inst = de_dicionario(EXEMPLO_MINIMO)
    assert inst.n == 3
    assert inst.elegiveis("CA1") == ("L2",)
    custo, _ = forca_bruta(inst)
    assert custo == pytest.approx(62.0)


def test_p_so_precisa_das_linhas_elegiveis() -> None:
    inst = de_dicionario(EXEMPLO_MINIMO)
    assert set(inst.elegiveis("TX1")) == {"L1", "L2"}
    assert set(inst.elegiveis("CA1")) == {"L2"}


def test_setup_assimetrico_e_preservado() -> None:
    """s[TX1,CA1] = 20 (montar) e s[CA1,TX1] = 11 (desmontar)."""
    inst = de_dicionario(EXEMPLO_MINIMO)
    assert inst.s("TX1", "CA1") == 20.0
    assert inst.s("CA1", "TX1") == 11.0


def test_setup_inicial_vem_do_no_ficticio() -> None:
    inst = de_dicionario(EXEMPLO_MINIMO)
    assert inst.s(inst.no_inicial, "CA1") == 12.0
    assert inst.s(inst.no_inicial, "TX1") == 8.0


def test_campo_obrigatorio_ausente() -> None:
    dados = json.loads(json.dumps(EXEMPLO_MINIMO))
    del dados["itens"][1]["d"]
    with pytest.raises(InstanciaInvalida, match="posição 2 não tem o campo 'd'"):
        de_dicionario(dados)


def test_item_sem_linha_elegivel() -> None:
    dados = json.loads(json.dumps(EXEMPLO_MINIMO))
    dados["itens"][0]["p"] = {}
    with pytest.raises(InstanciaInvalida, match="'TX1' não possui nenhuma linha"):
        de_dicionario(dados)


def test_setup_faltando() -> None:
    dados = json.loads(json.dumps(EXEMPLO_MINIMO))
    del dados["setup"]["TX2"]["CA1"]
    with pytest.raises(InstanciaInvalida, match=r"Setup ausente.*'TX2', 'CA1'"):
        de_dicionario(dados)


def test_arquivo_inexistente(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        carregar(tmp_path / "nao_existe.json")


def test_json_malformado(tmp_path) -> None:
    caminho = tmp_path / "quebrado.json"
    caminho.write_text("{ isto não é json", encoding="utf-8")
    with pytest.raises(InstanciaInvalida, match="não é JSON válido"):
        carregar(caminho)


def test_dicionario_gerado_tem_setup_aninhado() -> None:
    dados = para_dicionario(instancia_referencia())
    assert dados["setup"]["INI"]["CA1"] == 12.0
    assert dados["setup"]["TX3"]["CA1"] == 20.0
    assert dados["setup"]["CA1"]["TX3"] == 11.0
