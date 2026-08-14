"""Projeção compacta: identificação, título exato, envelope e rede de segurança."""

from __future__ import annotations

from metabooks_mcp.tools._compact import (
    compact_detail,
    compact_list,
    compact_product,
    compact_search,
)
from metabooks_mcp.tools.produtos import _title_term

from .fake_api import DETAIL_ONIX, FLAT_MAIN


def _envelope(items, **extra):
    return {"content": list(items), "totalElements": len(items), **extra}


# --- projeção de um produto -------------------------------------------------

def test_projeta_forma_plana():
    out = compact_product(FLAT_MAIN)
    assert out["titulo"] == "Dom Casmurro"
    assert out["isbn"] == "9788087062272"
    assert out["editora"] == "Editora Contexto"
    assert out["idioma"] == "Português"
    assert out["preco"] == "59.90 BRL"
    assert out["disponibilidade"] == "ativo"
    assert "sinopse" not in out and "descricao" not in out


def test_projeta_forma_onix_aninhada():
    out = compact_product(DETAIL_ONIX)
    assert out["titulo"] == "Dom Casmurro"
    # ISBN-13 vem do identificador tipo 15, não do ISBN-10 (tipo 02).
    assert out["isbn"] == "9788087062272"
    assert out["autores"] == ["Machado de Assis (Autor)", "Ana Trad (Tradutor)"]
    assert out["paginas"] == 256
    assert out["formato"] == "Livro (brochura)"


def test_disponibilidade_nao_inventa_rotulo_para_codigo_numerico():
    """productAvailability='40' não tem significado confiável — não virar texto."""
    out = compact_product({"title": "X", "productAvailability": "40", "active": False})
    assert out["disponibilidade"] == "inativo"


def test_rede_de_seguranca_para_schema_desconhecido():
    out = compact_product({"campoEstranho": "valor", "outro": ["a"] * 40})
    assert "_dados_brutos_reduzidos" in out


def test_shrink_limita_listas_longas():
    out = compact_product({"coisas": list(range(100))})
    reduzido = out["_dados_brutos_reduzidos"]["coisas"]
    assert len(reduzido) == 16 and "omitidos" in str(reduzido[-1])


# --- título exato / contém --------------------------------------------------

def test_titulo_exato_so_para_igualdade():
    data = _envelope([
        {"id": "1" * 32, "title": "Dom Casmurro"},
        {"id": "2" * 32, "title": "Análise de Dom Casmurro para o Enem"},
        {"id": "3" * 32, "title": "Dom Casmurro em quadrinhos"},
        {"id": "4" * 32, "title": "Memórias Póstumas"},
    ])
    por_titulo = {
        r["titulo"]: r for r in compact_search(data, termo="Dom Casmurro")["resultados"]
    }
    assert por_titulo["Dom Casmurro"]["titulo_exato"] is True
    for parcial in ("Análise de Dom Casmurro para o Enem", "Dom Casmurro em quadrinhos"):
        assert por_titulo[parcial]["titulo_exato"] is False
        assert por_titulo[parcial]["titulo_contem"] is True
    assert por_titulo["Memórias Póstumas"]["titulo_contem"] is False


def test_titulo_exato_ignora_acento_e_caixa():
    data = _envelope([{"id": "1" * 32, "title": "MEMÓRIAS PÓSTUMAS"}])
    out = compact_search(data, termo="memorias postumas")
    assert out["resultados"][0]["titulo_exato"] is True


def test_ordenacao_promove_exato_depois_parcial():
    data = _envelope([
        {"id": "1" * 32, "title": "Memórias Póstumas"},
        {"id": "2" * 32, "title": "Análise de Dom Casmurro"},
        {"id": "3" * 32, "title": "Dom Casmurro"},
    ])
    titulos = [r["titulo"] for r in compact_search(data, termo="Dom Casmurro")["resultados"]]
    assert titulos == ["Dom Casmurro", "Análise de Dom Casmurro", "Memórias Póstumas"]


def test_nao_reordena_quando_ha_ordenacao_explicita():
    data = _envelope([
        {"id": "1" * 32, "title": "Memórias Póstumas"},
        {"id": "2" * 32, "title": "Dom Casmurro"},
    ])
    out = compact_search(data, termo="Dom Casmurro", prioritize_exact=False)
    assert out["resultados"][0]["titulo"] == "Memórias Póstumas"


def test_aviso_quando_nenhum_titulo_bate():
    data = _envelope([
        {"id": "1" * 32, "title": "Outro livro"},
        {"id": "2" * 32, "title": "Terceiro livro"},
    ])
    assert "Nenhum título corresponde exatamente" in compact_search(
        data, termo="Dom Casmurro"
    )["aviso"]


def test_aviso_quando_ha_varios_exatos():
    data = _envelope([
        {"id": "1" * 32, "title": "Dom Casmurro", "isbn": "1"},
        {"id": "2" * 32, "title": "Dom Casmurro", "isbn": "2"},
    ])
    assert "2 títulos correspondem exatamente" in compact_search(
        data, termo="Dom Casmurro"
    )["aviso"]


def test_sem_aviso_quando_ha_exatamente_um_exato():
    data = _envelope([
        {"id": "1" * 32, "title": "Dom Casmurro"},
        {"id": "2" * 32, "title": "Outro"},
    ])
    assert "aviso" not in compact_search(data, termo="Dom Casmurro")


# --- envelope ---------------------------------------------------------------

def test_pagina_normalizada_para_base_1():
    """O parâmetro `page` é base 1; a resposta traz `number` base 0."""
    data = {"content": [], "totalElements": 0, "number": 0, "size": 50, "totalPages": 3}
    assert compact_search(data, None)["pagina"] == 1
    data["number"] = 2
    assert compact_search(data, None)["pagina"] == 3


def test_total_e_aviso_de_paginacao():
    data = {"content": [{"id": "1" * 32, "title": "X"}], "totalElements": 137}
    out = compact_search(data, None)
    assert out["total"] == 137 and out["mostrando"] == 1
    assert "137" in out["aviso_paginacao"]


def test_sem_aviso_de_paginacao_quando_completo():
    data = {"content": [{"id": "1" * 32, "title": "X"}], "totalElements": 1}
    assert "aviso_paginacao" not in compact_search(data, None)


def test_lista_nua_sem_envelope():
    out = compact_list([{"id": "1" * 32, "title": "X"}])
    assert out["total"] == 1 and out["resultados"][0]["titulo"] == "X"


def test_paginacao_nao_vem_de_dentro_de_um_produto():
    """Metadado de paginação só pode sair do nível de topo da resposta.

    Um produto pode ter `number` (número na série), `size` (tamanho do arquivo) e
    `count` — buscar em profundidade transformaria esses valores em página/total
    e o modelo reportaria uma paginação inventada.
    """
    data = {
        "content": [
            {"id": "1" * 32, "title": "X", "number": 7, "size": 99, "count": 42, "total": 500},
        ],
    }
    out = compact_search(data, None)
    assert out["total"] == 1, "o total tem de cair no fallback (itens mostrados)"
    assert out["mostrando"] == 1
    assert "pagina" not in out and "tamanho" not in out
    assert "aviso_paginacao" not in out


# --- detalhe ----------------------------------------------------------------

def test_detalhe_trunca_descricao():
    out = compact_detail(DETAIL_ONIX)
    assert out["resumo"]["descricao"].endswith("…")
    assert len(out["resumo"]["descricao"]) <= 401
    assert "detalhe_reduzido" in out


# --- extração do termo de título -------------------------------------------

def test_title_term():
    assert _title_term("Dom Casmurro") == "Dom Casmurro"
    assert _title_term("TI=Dom Casmurro") == "Dom Casmurro"
    assert _title_term('TI="Dom Casmurro" and PF=E*') == "Dom Casmurro"
    assert _title_term("ST=Linux and PF=E*") == "Linux"
    assert _title_term("(TI=Dom Casmurro or ST=Dom) and EJ=2020") == "Dom Casmurro"
    # Qualificadores que não são título não devem casar com nada.
    assert _title_term("AU=Machado") is None
    assert _title_term("IS=9788087062272") is None
    assert _title_term("VL=Contexto and AU=Machado") is None
