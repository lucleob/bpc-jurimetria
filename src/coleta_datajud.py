"""
Coleta de processos de BPC/LOAS na API Pública do DataJud (CNJ).

A API Pública do DataJud (https://datajud-wiki.cnj.jus.br/api-publica/) expõe
metadados processuais de todos os tribunais brasileiros em índices
Elasticsearch. Este módulo consulta os cinco Tribunais Regionais Federais
(TRF1–TRF5, incluindo os Juizados Especiais Federais, grau "JE") e extrai os
processos cujo assunto, na Tabela Processual Unificada (TPU/SGT) do CNJ,
corresponde ao Benefício de Prestação Continuada:

    6114  — Benefício Assistencial (Art. 203,V CF/88)   [código-pai]
    11946 — Deficiente                                   [filho de 6114]
    11947 — Idoso                                        [filho de 6114]

Os códigos-filhos foram identificados empiricamente por agregação de termos
sobre o índice público (a maioria dos registros traz apenas o código do
assunto, sem o nome).

Conformidade com a LGPD: a API pública do DataJud não expõe nomes de partes
nem documentos pessoais — apenas metadados processuais (classe, assunto,
órgão julgador, movimentos). Nenhum dado pessoal é coletado por este script.

Uso:
    python src/coleta_datajud.py --tribunais trf1 trf2 trf3 trf4 trf5 \
        --max-por-tribunal 500 --saida dados/

Saída: um arquivo JSONL (um processo por linha) por tribunal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# Chave pública de acesso divulgada na documentação oficial do DataJud.
# Caso o CNJ a rotacione, obtenha a atual em:
# https://datajud-wiki.cnj.jus.br/api-publica/acesso
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

BASE_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"

# Assuntos TPU/SGT que identificam o BPC/LOAS (ver docstring).
ASSUNTOS_BPC = [6114, 11946, 11947]

TAMANHO_PAGINA = 100          # máximo aceito pela API é 10.000; 100 é cortês
PAUSA_ENTRE_REQUISICOES = 0.3  # segundos
MAX_TENTATIVAS = 4


def consulta_base(depois_de: list | None = None) -> dict:
    """Monta o corpo da consulta Elasticsearch com paginação via search_after."""
    corpo: dict = {
        "size": TAMANHO_PAGINA,
        "track_total_hits": True,
        "query": {"terms": {"assuntos.codigo": ASSUNTOS_BPC}},
        "sort": [{"@timestamp": {"order": "asc"}}],
    }
    if depois_de is not None:
        corpo["search_after"] = depois_de
    return corpo


def requisita(url: str, corpo: dict) -> dict:
    """POST com tentativas e recuo exponencial para erros transitórios."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resposta = requests.post(
                url,
                json=corpo,
                headers={"Authorization": f"APIKey {API_KEY}"},
                timeout=60,
            )
            if resposta.status_code == 200:
                return resposta.json()
            if resposta.status_code in (429, 500, 502, 503, 504):
                espera = 2 ** tentativa
                print(f"  HTTP {resposta.status_code}; aguardando {espera}s...")
                time.sleep(espera)
                continue
            resposta.raise_for_status()
        except requests.RequestException as erro:
            if tentativa == MAX_TENTATIVAS:
                raise
            espera = 2 ** tentativa
            print(f"  Erro de rede ({erro}); nova tentativa em {espera}s...")
            time.sleep(espera)
    raise RuntimeError("Número máximo de tentativas excedido.")


def coleta_tribunal(tribunal: str, max_processos: int, pasta_saida: Path) -> int:
    """Coleta processos de um tribunal e grava em JSONL. Retorna o total gravado."""
    url = BASE_URL.format(tribunal=tribunal)
    arquivo = pasta_saida / f"bpc_{tribunal}.jsonl"
    gravados = 0
    depois_de: list | None = None

    with arquivo.open("w", encoding="utf-8") as saida:
        while gravados < max_processos:
            dados = requisita(url, consulta_base(depois_de))
            acertos = dados["hits"]["hits"]
            if not acertos:
                break
            if depois_de is None:  # primeira página: informa o universo total
                total = dados["hits"]["total"]["value"]
                print(f"[{tribunal.upper()}] universo BPC no índice: {total:,} processos")
            for acerto in acertos:
                saida.write(json.dumps(acerto["_source"], ensure_ascii=False) + "\n")
                gravados += 1
                if gravados >= max_processos:
                    break
            depois_de = acertos[-1]["sort"]
            time.sleep(PAUSA_ENTRE_REQUISICOES)

    print(f"[{tribunal.upper()}] gravados {gravados} processos em {arquivo}")
    return gravados


def principal() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    analisador.add_argument(
        "--tribunais", nargs="+",
        default=["trf1", "trf2", "trf3", "trf4", "trf5"],
        choices=["trf1", "trf2", "trf3", "trf4", "trf5"],
        help="Tribunais a consultar (padrão: os cinco TRFs).",
    )
    analisador.add_argument(
        "--max-por-tribunal", type=int, default=500,
        help="Máximo de processos por tribunal (padrão: 500; amostra de demonstração).",
    )
    analisador.add_argument(
        "--saida", type=Path, default=Path("dados"),
        help="Pasta de saída dos arquivos JSONL (padrão: dados/).",
    )
    argumentos = analisador.parse_args()
    argumentos.saida.mkdir(parents=True, exist_ok=True)

    total_geral = 0
    for tribunal in argumentos.tribunais:
        total_geral += coleta_tribunal(
            tribunal, argumentos.max_por_tribunal, argumentos.saida
        )
    print(f"\nColeta concluída: {total_geral} processos no total.")


if __name__ == "__main__":
    sys.exit(principal())

