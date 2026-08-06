#!/usr/bin/env python3
"""Rodada de validação contra a API REAL da Metabooks — somente leitura.

O que faz
---------
Confere, contra produção, as premissas que a suíte de testes só consegue
simular: nomes de campos, base da paginação, limites aceitos, negociação de
``Accept``, host das URLs de mídia e quais qualificadores de busca realmente
funcionam. Gera um relatório para revisão.

O que NÃO faz
-------------
* Não escreve nada na Metabooks (só GET e os POST de busca).
* Não imprime nem grava credenciais: todo valor de token/senha é substituído
  por ``***`` antes de sair.
* Não inclui conteúdo do catálogo por padrão. O relatório traz a FORMA das
  respostas (nomes de chaves e tipos), não sinopses, títulos ou preços. Use
  ``--incluir-amostras`` só se precisar e só para revisão interna.

Uso
---
    export METABOOKS_USERNAME=...        # ou METABOOKS_METADATA_TOKEN=...
    export METABOOKS_PASSWORD=...
    export METABOOKS_COVER_TOKEN=...     # opcional
    export METABOOKS_MMO_TOKEN=...       # opcional
    python scripts/smoke_live.py

    # variantes
    python scripts/smoke_live.py --isbn 9788575228517 --editora BR0090053
    python scripts/smoke_live.py --base-url https://staging.kubernetes.br.metabooks.com/api/v2
    python scripts/smoke_live.py --saida relatorio.md --incluir-amostras

Faz UM único login e desloga no fim: cada login ocupa um slot de sessão
paralela da MVB, liberado de outra forma só após 60 min.

Código de saída: 0 se nada falhou, 1 se houve FALHA (avisos não reprovam).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx  # noqa: E402

from metabooks_mcp.client import MetabooksClient, MetabooksError  # noqa: E402

OK, FALHA, AVISO, INFO, PULADO = "OK", "FALHA", "AVISO", "INFO", "PULADO"

# Campos que `tools/_compact.py` espera em cada forma da resposta. Se a API
# renomear qualquer um, a projeção compacta empobrece silenciosamente — é
# exatamente isso que esta rodada precisa detectar.
CAMPOS_PLANOS = [
    "id", "isbn", "title", "subTitle", "publisher", "publicationDate",
    "productType", "productFormId", "priceBrl", "author", "state", "language",
]
CAMPOS_DETALHE = [
    "titles", "identifiers", "contributors", "prices", "form", "extent",
    "languages", "publishers",
]
CHAVES_ENVELOPE = ["content", "totalElements", "number", "size", "totalPages"]

CAMPOS_INDICE = [
    "author", "publisher", "title", "keyword", "set", "collection", "identifier",
]
# Qualificadores anunciados no help das tools. A API devolve 0 resultados (não
# erro) para um qualificador que não existe, então "0" aqui é sinal de alerta.
QUALIFICADORES = [
    ("ST", "ST=Linux"), ("TI", "TI=Linux"), ("AU", "AU=Machado"),
    ("VL", "VL=Novatec"), ("IS", "IS=9788575228517"), ("SW", "SW=programação"),
    ("PF", "PF=E*"), ("PR", "PR=40^80"), ("EJ", "EJ=2020"),
    ("AD", "AD=20240101^20241231"), ("RH", "RH=AAABX01"),
]


@dataclass
class Resultado:
    nome: str
    status: str
    detalhe: str = ""
    dados: dict = field(default_factory=dict)


class Rodada:
    def __init__(self, client: MetabooksClient, args: argparse.Namespace) -> None:
        self.client = client
        self.args = args
        self.resultados: list[Resultado] = []
        self.segredos = [
            s for s in (
                client.password, client.metadata_token,
                client.cover_token, client.mmo_token,
            ) if s
        ]
        self.isbn: str | None = args.isbn
        self.uuid: str | None = args.uuid
        self.editora: str | None = args.editora

    # --- saída ------------------------------------------------------------

    def scrub(self, texto: Any) -> Any:
        """Remove credenciais e tokens de qualquer texto que vá para o relatório."""
        if not isinstance(texto, str):
            return texto
        for segredo in self.segredos:
            if segredo:
                texto = texto.replace(segredo, "***")
        # Tokens que apareçam em cabeçalhos/URLs ecoados por mensagens de erro.
        texto = re.sub(r"(?i)(bearer\s+)\S+", r"\1***", texto)
        texto = re.sub(r"(?i)(access_token=)[^&\s]+", r"\1***", texto)
        return texto

    def registra(self, nome: str, status: str, detalhe: str = "", **dados) -> Resultado:
        r = Resultado(nome, status, self.scrub(detalhe), {
            k: (self.scrub(v) if isinstance(v, str) else v) for k, v in dados.items()
        })
        self.resultados.append(r)
        marca = {OK: "  ok  ", FALHA: " FALHA", AVISO: " aviso", INFO: " info ",
                 PULADO: "pulado"}[status]
        linha = f"[{marca}] {nome}"
        if r.detalhe:
            linha += f" — {r.detalhe}"
        print(linha, flush=True)
        return r

    # --- utilidades -------------------------------------------------------

    @staticmethod
    def forma(obj: Any, profundidade: int = 3, max_chaves: int = 40) -> Any:
        """Descreve a ESTRUTURA de uma resposta sem expor valores.

        Dicts viram {chave: tipo}, listas viram ['<n itens>', forma-do-primeiro].
        É o que permite validar os nomes de campo esperados por `_compact.py`
        sem colocar metadados de clientes no relatório.
        """
        if profundidade <= 0:
            return "…"
        if isinstance(obj, dict):
            out = {}
            for i, (k, v) in enumerate(obj.items()):
                if i >= max_chaves:
                    out["…"] = f"+{len(obj) - max_chaves} chaves"
                    break
                out[k] = Rodada.forma(v, profundidade - 1, max_chaves)
            return out
        if isinstance(obj, list):
            if not obj:
                return ["<vazio>"]
            return [f"<{len(obj)} itens>", Rodada.forma(obj[0], profundidade - 1, max_chaves)]
        if obj is None:
            return "null"
        if isinstance(obj, bool):
            return "bool"
        if isinstance(obj, (int, float)):
            return "número"
        if isinstance(obj, str):
            return f"texto({len(obj)})"
        return type(obj).__name__

    def amostra(self, obj: Any) -> Any:
        """Valores reais, só quando explicitamente pedido."""
        if not self.args.incluir_amostras:
            return None
        return json.loads(self.scrub(json.dumps(obj, ensure_ascii=False))[:4000])

    async def status_de(self, metodo: str, path: str, **kwargs) -> tuple[int | None, Any]:
        """Executa a chamada e devolve (status, corpo-ou-erro), sem levantar."""
        try:
            if metodo == "GET":
                return 200, await self.client.get(path, **kwargs)
            return 200, await self.client.post(path, **kwargs)
        except httpx.HTTPStatusError as exc:
            return exc.response.status_code, exc.response.text[:300]
        except MetabooksError as exc:
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"

    # --- checagens --------------------------------------------------------

    async def login(self) -> bool:
        inicio = time.monotonic()
        try:
            token = await self.client._get_metadata_token()
        except Exception as exc:  # noqa: BLE001
            self.registra("login", FALHA, f"{type(exc).__name__}: {exc}")
            return False
        ms = int((time.monotonic() - inicio) * 1000)
        modo = "token estático" if self.client.metadata_token else "usuário/senha"
        self.registra(
            "login", OK, f"{modo}, {ms} ms",
            tamanho_do_token=len(token),
            # `_do_login` aceita token como texto cru E como JSON; qual chegou?
            formato_aceito="texto cru ou JSON (tratados)",
        )
        return True

    async def descobre_ids(self) -> None:
        """Obtém um UUID/ISBN do catálogo do próprio usuário para as demais provas."""
        if self.uuid and self.isbn:
            self.registra("ids de prova", INFO, "informados por argumento")
            return
        status, corpo = await self.status_de(
            "GET", "products", params={"page": 1, "size": 5, "search": self.args.busca}
        )
        if status != 200 or not isinstance(corpo, dict):
            self.registra(
                "ids de prova", FALHA,
                f"busca inicial falhou (HTTP {status}); passe --isbn/--uuid",
                resposta=self.forma(corpo),
            )
            return
        itens = corpo.get("content") or []
        if not itens:
            self.registra(
                "ids de prova", FALHA,
                f"busca por {self.args.busca!r} não devolveu nada; use --busca ou --isbn/--uuid",
            )
            return
        primeiro = itens[0]
        self.uuid = self.uuid or primeiro.get("id")
        self.isbn = self.isbn or primeiro.get("isbn") or primeiro.get("isbn13")
        self.registra(
            "ids de prova", OK,
            f"uuid={'sim' if self.uuid else 'não'}, isbn={'sim' if self.isbn else 'não'}",
        )

    async def checa_busca(self) -> None:
        # 1) json-short devolve os campos planos que a projeção espera?
        for accept, rotulo in (
            ("application/json-short", "json-short"),
            ("application/json", "json (long)"),
        ):
            status, corpo = await self.status_de(
                "GET", "products",
                params={"page": 1, "size": 3, "search": self.args.busca},
                accept=accept,
            )
            if status != 200 or not isinstance(corpo, dict):
                self.registra(f"busca {rotulo}", FALHA, f"HTTP {status}",
                              resposta=self.forma(corpo))
                continue
            itens = corpo.get("content") or []
            presentes = [c for c in CAMPOS_PLANOS if itens and c in itens[0]]
            ausentes = [c for c in CAMPOS_PLANOS if not itens or c not in itens[0]]
            self.registra(
                f"busca {rotulo}", OK if not ausentes else AVISO,
                f"{len(presentes)}/{len(CAMPOS_PLANOS)} campos esperados"
                + (f"; AUSENTES: {', '.join(ausentes)}" if ausentes else ""),
                forma_do_item=self.forma(itens[0]) if itens else None,
                amostra=self.amostra(itens[0]) if itens else None,
            )
            faltando_env = [k for k in CHAVES_ENVELOPE if k not in corpo]
            self.registra(
                f"envelope de paginação ({rotulo})",
                OK if not faltando_env else AVISO,
                f"chaves ausentes: {', '.join(faltando_env)}" if faltando_env
                else "todas as chaves esperadas presentes",
                forma_do_envelope=self.forma(
                    {k: v for k, v in corpo.items() if k != "content"}, profundidade=2
                ),
            )

        # 2) `number` é base 0 ou base 1? A normalização de `pagina` depende disso.
        observado = {}
        for pagina in (1, 2):
            status, corpo = await self.status_de(
                "GET", "products",
                params={"page": pagina, "size": 3, "search": self.args.busca},
            )
            if status == 200 and isinstance(corpo, dict):
                observado[f"page={pagina}"] = corpo.get("number")
        base_zero = observado.get("page=1") == 0
        self.registra(
            "base da paginação", OK if base_zero else FALHA,
            f"page=1 devolve number={observado.get('page=1')!r}, "
            f"page=2 devolve number={observado.get('page=2')!r}. "
            + ("Base 0 confirmada: `pagina` = number + 1 está correto."
               if base_zero else
               "NÃO é base 0 — a normalização de `pagina` em _compact._envelope "
               "precisa ser revista."),
            observado=observado,
        )

        # 3) limites de `size` e `page`
        for valor, esperado in ((250, "aceito"), (251, "recusado"), (0, "recusado")):
            status, _ = await self.status_de(
                "GET", "products", params={"page": 1, "size": valor, "search": self.args.busca}
            )
            aceito = status == 200
            coerente = (esperado == "aceito") == aceito
            self.registra(
                f"size={valor}", OK if coerente else AVISO,
                f"HTTP {status} ({'aceito' if aceito else 'recusado'}; "
                f"o MCP assume {esperado})",
            )

        # 4) filtro `active`
        for valor in ("true", "false"):
            status, corpo = await self.status_de(
                "GET", "products",
                params={"page": 1, "size": 3, "search": self.args.busca, "active": valor},
            )
            total = corpo.get("totalElements") if isinstance(corpo, dict) else None
            self.registra(f"active={valor}", OK if status == 200 else AVISO,
                          f"HTTP {status}, total={total}")

        # 5) ordenação
        status, _ = await self.status_de(
            "GET", "products",
            params={"page": 1, "size": 3, "search": self.args.busca,
                    "sort": "identifier", "direction": "asc"},
        )
        self.registra("sort=identifier&direction=asc", OK if status == 200 else AVISO,
                      f"HTTP {status}")

    async def checa_qualificadores(self) -> None:
        """Um qualificador inexistente devolve 0 resultados, não erro."""
        for chave, expressao in QUALIFICADORES:
            status, corpo = await self.status_de(
                "GET", "products", params={"page": 1, "size": 1, "search": expressao}
            )
            total = corpo.get("totalElements") if isinstance(corpo, dict) else None
            if status != 200:
                self.registra(f"qualificador {chave}", FALHA, f"HTTP {status}")
            elif total:
                self.registra(f"qualificador {chave}", OK, f"{total} resultados")
            else:
                self.registra(
                    f"qualificador {chave}", AVISO,
                    f"0 resultados para {expressao!r} — pode ser catálogo sem "
                    "correspondência OU qualificador inexistente; confira à mão",
                )

    async def checa_lote(self) -> None:
        if not self.isbn:
            self.registra("busca em lote", PULADO, "sem ISBN de prova")
            return
        corpo = {"content": [{"isbn": self.isbn}]}
        for accept, rotulo in (
            ("application/json-short", "json-short"),
            ("application/json", "json"),
        ):
            status, resp = await self.status_de(
                "POST", "products", json=corpo,
                params={"page": 1, "size": 10}, accept=accept,
            )
            itens = (resp.get("content") or []) if isinstance(resp, dict) else []
            self.registra(
                f"POST /products ({rotulo})", OK if status == 200 else FALHA,
                f"HTTP {status}, {len(itens)} item(ns)"
                + ("" if status == 200 else
                   " — o MCP envia Content-Type: application/json; se o servidor "
                   "exigir json-short, client.post precisa espelhar o Accept"),
                forma=self.forma(itens[0]) if itens else None,
            )

    async def checa_detalhe(self) -> None:
        if not self.uuid:
            self.registra("detalhe do produto", PULADO, "sem UUID de prova")
            return
        status, corpo = await self.status_de("GET", f"product/{self.uuid}")
        if status != 200 or not isinstance(corpo, dict):
            self.registra("detalhe (json)", FALHA, f"HTTP {status}",
                          resposta=self.forma(corpo))
        else:
            ausentes = [c for c in CAMPOS_DETALHE if c not in corpo]
            self.registra(
                "detalhe (json)", OK if not ausentes else AVISO,
                f"chaves ausentes: {', '.join(ausentes)}" if ausentes
                else "estrutura aninhada conforme esperado",
                forma=self.forma(corpo, profundidade=3),
                amostra=self.amostra(corpo),
            )
            # ISBN-13 vem de identifiers[] filtrado por productIdentifierType=15.
            tipos = sorted({
                str(i.get("productIdentifierType"))
                for i in (corpo.get("identifiers") or []) if isinstance(i, dict)
            })
            self.registra(
                "tipos de identificador", OK if "15" in tipos else AVISO,
                f"presentes: {tipos or 'nenhum'}"
                + ("" if "15" in tipos else
                   " — sem o tipo 15 o ISBN-13 do detalhe compacto sai errado"),
            )
            # Extrai o MVB ID da editora para a checagem de /publisher.
            if not self.editora:
                for pub in (corpo.get("publishers") or []):
                    if isinstance(pub, dict):
                        for chave in ("mvbId", "mvbid", "publisherId", "id"):
                            if pub.get(chave):
                                self.editora = str(pub[chave])
                                break
                    if self.editora:
                        break

        for formato in ("onix30-short", "onix30-ref"):
            status, corpo = await self.status_de(
                "GET", f"product/{self.uuid}", accept=f"application/{formato}"
            )
            xml = isinstance(corpo, str) and corpo.lstrip().startswith("<")
            self.registra(
                formato, OK if status == 200 and xml else FALHA,
                f"HTTP {status}, {'XML' if xml else 'não parece XML'}"
                f"{'' if xml else f' — início: {str(corpo)[:60]!r}'}",
            )

        if self.isbn:
            for id_type in ("isbn13", "ean", "gtin"):
                status, _ = await self.status_de("GET", f"product/{self.isbn}/{id_type}")
                self.registra(
                    f"detalhe por {id_type}",
                    OK if status == 200 else AVISO,
                    f"HTTP {status}" + ("" if status == 200 else
                                        " (pode ser normal se o ID não for desse tipo)"),
                )

    async def checa_multiple_products(self) -> None:
        if not self.uuid:
            self.registra("multipleProducts", PULADO, "sem UUID de prova")
            return
        status, corpo = await self.status_de(
            "POST", "product/multipleProducts", json={"ids": [self.uuid]}
        )
        itens = (corpo.get("content") or []) if isinstance(corpo, dict) else []
        self.registra(
            "multipleProducts (json)", OK if status == 200 else FALHA,
            f"HTTP {status}, {len(itens)} item(ns)",
            forma=self.forma(corpo, profundidade=2),
        )
        # A collection anota "only in json format" — o MCP passou a nunca pedir
        # json-short aqui. Esta prova confirma se a restrição é real.
        status_short, _ = await self.status_de(
            "POST", "product/multipleProducts", json={"ids": [self.uuid]},
            accept="application/json-short",
        )
        if status_short == 200:
            self.registra(
                "multipleProducts (json-short)", INFO,
                "HTTP 200 — o servidor ACEITA json-short, ao contrário do que a "
                "collection anota. Não é um problema (o MCP usa json), mas a "
                "restrição documentada não se confirma.",
            )
        else:
            self.registra(
                "multipleProducts (json-short)", OK,
                f"HTTP {status_short} — restrição da collection confirmada",
            )

    async def checa_indice(self) -> None:
        for campo in CAMPOS_INDICE:
            status, corpo = await self.status_de("GET", f"index/{campo}/{self.args.termo_indice}")
            n = len(corpo) if isinstance(corpo, list) else None
            if status == 200:
                self.registra(f"index/{campo}", OK, f"{n} entrada(s)",
                              forma=self.forma(corpo[0]) if isinstance(corpo, list) and corpo else None)
            else:
                self.registra(
                    f"index/{campo}", AVISO,
                    f"HTTP {status} — se este índice não existe, remova-o do "
                    "Literal de metabooks_index_search",
                )

    async def checa_editora(self) -> None:
        if not self.editora:
            self.registra("publisher", PULADO,
                          "sem MVB ID; passe --editora BR00xxxxx para checar")
            return
        status, corpo = await self.status_de("GET", f"publisher/{self.editora}")
        self.registra(
            "publisher", OK if status == 200 else FALHA, f"HTTP {status}",
            forma=self.forma(corpo, profundidade=2) if status == 200 else None,
        )

    async def checa_capa(self) -> None:
        if not self.client.cover_token:
            self.registra("capa", PULADO, "METABOOKS_COVER_TOKEN não configurado")
            return
        if not self.isbn:
            self.registra("capa", PULADO, "sem ISBN de prova")
            return
        # A negociação de Accept é uma afirmação forte no código: */* funciona,
        # image/jpeg dá 406 e image/* dá 403.
        esperado = {"*/*": 200, "image/jpeg": 406, "image/*": 403}
        for accept, alvo in esperado.items():
            try:
                dados = await self.client.get_bytes(
                    f"cover/{self.isbn}/m", scope="cover", accept=accept
                )
                status, tamanho = 200, len(dados)
            except httpx.HTTPStatusError as exc:
                status, tamanho = exc.response.status_code, 0
            except Exception as exc:  # noqa: BLE001
                self.registra(f"capa Accept={accept}", FALHA, f"{type(exc).__name__}: {exc}")
                continue
            self.registra(
                f"capa Accept={accept}",
                OK if status == alvo else AVISO,
                f"HTTP {status} (código documentado: {alvo})"
                + (f", {tamanho} bytes" if tamanho else ""),
            )
        for tamanho_nome in ("s", "m", "l", ""):
            path = f"cover/{self.isbn}" + (f"/{tamanho_nome}" if tamanho_nome else "")
            try:
                dados = await self.client.get_bytes(path, scope="cover", accept="*/*")
                jpeg = dados[:3] == b"\xff\xd8\xff"
                self.registra(
                    f"capa tamanho {tamanho_nome or 'original'}", OK if jpeg else AVISO,
                    f"{len(dados) / 1024:.1f} KB, {'JPEG' if jpeg else 'NÃO é JPEG'}",
                )
            except Exception as exc:  # noqa: BLE001
                self.registra(f"capa tamanho {tamanho_nome or 'original'}", AVISO,
                              f"{type(exc).__name__}: {exc}")

    async def checa_midia(self) -> None:
        if not self.client.mmo_token:
            self.registra("mídia/MMO", PULADO, "METABOOKS_MMO_TOKEN não configurado")
            return
        if not self.uuid:
            self.registra("mídia/MMO", PULADO, "sem UUID de prova")
            return
        status, corpo = await self.status_de("GET", f"asset/mmo/{self.uuid}", scope="mmo")
        if status != 200 or not isinstance(corpo, list):
            self.registra("listagem de mídia", AVISO,
                          f"HTTP {status} (o título pode não ter mídias)",
                          resposta=self.forma(corpo))
            return
        self.registra(
            "listagem de mídia", OK, f"{len(corpo)} asset(s)",
            forma=self.forma(corpo[0]) if corpo else None,
            tipos=sorted({str(a.get("type")) for a in corpo if isinstance(a, dict)}),
        )
        # CRÍTICO: a guarda anti-SSRF endurecida exige mesmo esquema, host, porta
        # e prefixo /api. Se a MVB servir os arquivos de outro host (CDN), a
        # guarda passa a bloquear mídia legítima — é a principal regressão
        # possível desta versão.
        base = urlparse(self.client.base_url)
        for asset in corpo:
            if not isinstance(asset, dict) or not asset.get("url"):
                continue
            url = asset["url"]
            alvo = urlparse(url)
            aceita = self.client._same_api_host(url)
            self.registra(
                f"URL de mídia ({asset.get('type')})",
                OK if aceita else FALHA,
                ("dentro da guarda de host" if aceita else
                 "BLOQUEADA pela guarda de host — mídia legítima seria recusada; "
                 "a guarda em client._same_api_host precisa acomodar este destino"),
                esquema=alvo.scheme, mesmo_host=alvo.hostname == base.hostname,
                porta=alvo.port, prefixo_do_path="/".join(alvo.path.split("/")[:3]),
            )
        # Baixa um arquivo de verdade para fechar o ciclo.
        primeiro = next(
            (a for a in corpo if isinstance(a, dict) and a.get("url")
             and "/asset/mmo/file/" in a["url"]), None
        )
        if primeiro:
            try:
                dados = await self.client.get_bytes_from_url(
                    primeiro["url"], scope="mmo", accept="*/*"
                )
                self.registra("download de mídia", OK,
                              f"{primeiro.get('type')}, {len(dados) / 1024:.1f} KB, "
                              f"início {dados[:4]!r}")
            except Exception as exc:  # noqa: BLE001
                self.registra("download de mídia", FALHA, f"{type(exc).__name__}: {exc}")

    # --- orquestração -----------------------------------------------------

    async def executar(self) -> None:
        self.registra("ambiente", INFO, f"base_url={self.client.base_url}")
        if not await self.login():
            return
        await self.descobre_ids()
        await self.checa_busca()
        await self.checa_qualificadores()
        await self.checa_lote()
        await self.checa_detalhe()
        await self.checa_multiple_products()
        await self.checa_indice()
        await self.checa_editora()
        await self.checa_capa()
        await self.checa_midia()

    # --- relatório --------------------------------------------------------

    def relatorio_markdown(self) -> str:
        contagem = {s: sum(1 for r in self.resultados if r.status == s)
                    for s in (OK, FALHA, AVISO, INFO, PULADO)}
        linhas = [
            "# Rodada de validação — API real Metabooks",
            "",
            f"- Base: `{self.client.base_url}`",
            f"- Autenticação: {'token estático' if self.client.metadata_token else 'usuário/senha'}",
            f"- Token de capa: {'sim' if self.client.cover_token else 'não'}"
            f" · Token de MMO: {'sim' if self.client.mmo_token else 'não'}",
            f"- Amostras de conteúdo: {'INCLUÍDAS' if self.args.incluir_amostras else 'omitidas (só a forma das respostas)'}",
            "",
            f"**{contagem[OK]} ok · {contagem[FALHA]} falha(s) · {contagem[AVISO]} aviso(s)"
            f" · {contagem[PULADO]} pulado(s)**",
            "",
        ]
        for rotulo, titulo in ((FALHA, "Falhas"), (AVISO, "Avisos")):
            itens = [r for r in self.resultados if r.status == rotulo]
            if itens:
                linhas += [f"## {titulo}", ""]
                linhas += [f"- **{r.nome}** — {r.detalhe}" for r in itens]
                linhas.append("")
        linhas += ["## Todas as checagens", "", "| Checagem | Status | Detalhe |",
                   "|---|---|---|"]
        for r in self.resultados:
            detalhe = r.detalhe.replace("|", "\\|").replace("\n", " ")
            linhas.append(f"| {r.nome} | {r.status} | {detalhe} |")
        linhas += ["", "## Formas observadas", "",
                   "```json",
                   json.dumps(
                       {r.nome: r.dados for r in self.resultados if r.dados},
                       ensure_ascii=False, indent=2,
                   ),
                   "```", ""]
        return "\n".join(linhas)

    def houve_falha(self) -> bool:
        return any(r.status == FALHA for r in self.resultados)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validação somente leitura contra a API real da Metabooks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--base-url", default=os.environ.get("METABOOKS_BASE_URL"),
                   help="URL base (padrão: produção)")
    p.add_argument("--isbn", help="ISBN-13 de prova (padrão: o 1º da busca inicial)")
    p.add_argument("--uuid", help="UUID de produto de prova")
    p.add_argument("--editora", help="MVB ID de editora (ex.: BR0090053)")
    p.add_argument("--busca", default="Linux",
                   help="Termo da busca inicial, usado para achar os IDs de prova")
    p.add_argument("--termo-indice", default="Mach",
                   help="Prefixo usado nas consultas de índice")
    p.add_argument("--saida", default="smoke-report.md",
                   help="Arquivo do relatório (padrão: smoke-report.md)")
    p.add_argument("--incluir-amostras", action="store_true",
                   help="Inclui VALORES do catálogo no relatório (padrão: só a forma). "
                        "Use apenas para revisão interna.")
    return p.parse_args()


async def main() -> int:
    args = parse_args()
    client = MetabooksClient(
        username=os.environ.get("METABOOKS_USERNAME"),
        password=os.environ.get("METABOOKS_PASSWORD"),
        metadata_token=os.environ.get("METABOOKS_METADATA_TOKEN"),
        cover_token=os.environ.get("METABOOKS_COVER_TOKEN"),
        mmo_token=os.environ.get("METABOOKS_MMO_TOKEN"),
        base_url=args.base_url,
    )
    if not any((client.username and client.password, client.metadata_token)):
        print(
            "Sem credenciais. Defina METABOOKS_USERNAME + METABOOKS_PASSWORD "
            "ou METABOOKS_METADATA_TOKEN antes de rodar.",
            file=sys.stderr,
        )
        return 2

    rodada = Rodada(client, args)
    try:
        await rodada.executar()
    finally:
        # Libera o slot de sessão paralela da MVB.
        await client.logout()
        await client.aclose()

    destino = Path(args.saida)
    destino.write_text(rodada.relatorio_markdown(), encoding="utf-8")
    print(f"\nRelatório: {destino.resolve()}")
    if rodada.houve_falha():
        print("Houve FALHAS — veja a seção 'Falhas' do relatório.")
        return 1
    print("Nenhuma falha. Confira os avisos antes de liberar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
