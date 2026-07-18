"""
Métricas jurimétricas sobre os processos de BPC/LOAS coletados do DataJud.

Lê os arquivos JSONL produzidos por `coleta_datajud.py` e calcula, por
tribunal, ano de ajuizamento e grau (JEF vs. justiça comum):

  1. volume de ajuizamentos;
  2. duração (dias entre o ajuizamento e o último movimento registrado);
  3. desfecho da sentença de mérito, classificado pelos códigos de movimento
     da Tabela Processual Unificada (SGT/CNJ);
  4. tabela exploratória de frequência de movimentos (para auditar e
     estender o classificador).

Classificação de desfecho (movimentos de julgamento do SGT):
    219 — Procedência                      → favorável ao requerente
    221 — Procedência em parte             → favorável ao requerente
    220 — Improcedência                    → desfavorável
    466 — Homologação de Transação (acordo) → acordo
    228 — Homologação de transação (variante)→ acordo

Movimentos com nome disponível também são cotejados por expressão regular,
como salvaguarda para registros sem código reconhecido.

Uso:
    python src/analise_metricas.py --entrada dados/ --saida dados/
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

MOVIMENTOS_FAVORAVEIS = {219, 221}
MOVIMENTOS_DESFAVORAVEIS = {220}
MOVIMENTOS_ACORDO = {228, 466}

PADRAO_FAVORAVEL = re.compile(r"\bprocedência\b|\bprocedente", re.IGNORECASE)
PADRAO_DESFAVORAVEL = re.compile(r"improced", re.IGNORECASE)
PADRAO_ACORDO = re.compile(r"transação|acordo|conciliação homolog", re.IGNORECASE)

ANO_MINIMO, ANO_MAXIMO = 1990, datetime.now().year  # descarta datas corrompidas


def interpreta_data(valor: str | int | None) -> datetime | None:
    """Interpreta datas nos formatos usados pelo DataJud."""
    if not valor:
        return None
    valor = str(valor).rstrip("Z").replace("T", "").replace("-", "").replace(":", "")
    valor = valor.split(".")[0]
    for tamanho, formato in ((14, "%Y%m%d%H%M%S"), (8, "%Y%m%d")):
        try:
            return datetime.strptime(valor[:tamanho], formato)
        except ValueError:
            continue
    return None


def classifica_desfecho(movimentos: list[dict]) -> str:
    """Classifica o desfecho de mérito a partir dos movimentos do processo."""
    resultado = "sem sentença identificada"
    for movimento in movimentos or []:
        codigo = movimento.get("codigo")
        nome = movimento.get("nome") or ""
        if codigo in MOVIMENTOS_FAVORAVEIS or (
            PADRAO_FAVORAVEL.search(nome) and not PADRAO_DESFAVORAVEL.search(nome)
        ):
            resultado = "favorável"
        elif codigo in MOVIMENTOS_DESFAVORAVEIS or PADRAO_DESFAVORAVEL.search(nome):
            resultado = "desfavorável"
        elif codigo in MOVIMENTOS_ACORDO or PADRAO_ACORDO.search(nome):
            resultado = "acordo"
    return resultado  # prevalece a última sentença na linha do tempo


def carrega_processos(pasta: Path) -> pd.DataFrame:
    """Consolida os JSONL em um DataFrame com uma linha por processo."""
    linhas = []
    for arquivo in sorted(pasta.glob("bpc_*.jsonl")):
        with arquivo.open(encoding="utf-8") as origem:
            for texto in origem:
                processo = json.loads(texto)
                movimentos = processo.get("movimentos") or []
                ajuizamento = interpreta_data(processo.get("dataAjuizamento"))
                datas_movimentos = [
                    d for d in (interpreta_data(m.get("dataHora")) for m in movimentos) if d
                ]
                ultimo = max(datas_movimentos) if datas_movimentos else None
                duracao = (
                    (ultimo - ajuizamento).days
                    if ajuizamento and ultimo and ultimo >= ajuizamento
                    else None
                )
                linhas.append(
                    {
                        "tribunal": processo.get("tribunal"),
                        "grau": processo.get("grau"),
                        "numero": processo.get("numeroProcesso"),
                        "classe": (processo.get("classe") or {}).get("nome"),
                        "orgao": (processo.get("orgaoJulgador") or {}).get("nome"),
                        "ano_ajuizamento": ajuizamento.year if ajuizamento else None,
                        "duracao_dias": duracao,
                        "qtd_movimentos": len(movimentos),
                        "desfecho": classifica_desfecho(movimentos),
                    }
                )
    quadro = pd.DataFrame(linhas).drop_duplicates(subset=["numero", "grau"])
    quadro = quadro[
        quadro["ano_ajuizamento"].between(ANO_MINIMO, ANO_MAXIMO, inclusive="both")
        | quadro["ano_ajuizamento"].isna()
    ]
    return quadro


def frequencia_movimentos(pasta: Path) -> pd.DataFrame:
    """Tabela exploratória: frequência dos códigos de movimento na amostra."""
    contagem: dict[tuple, int] = {}
    for arquivo in sorted(pasta.glob("bpc_*.jsonl")):
        with arquivo.open(encoding="utf-8") as origem:
            for texto in origem:
                for movimento in json.loads(texto).get("movimentos") or []:
                    chave = (movimento.get("codigo"), movimento.get("nome"))
                    contagem[chave] = contagem.get(chave, 0) + 1
    quadro = pd.DataFrame(
        [{"codigo": c, "nome": n, "ocorrencias": q} for (c, n), q in contagem.items()]
    )
    return quadro.sort_values("ocorrencias", ascending=False)


def grafico_barras(serie: pd.Series, titulo: str, rotulo_y: str, destino: Path) -> None:
    figura, eixo = plt.subplots(figsize=(8, 4.5))
    serie.plot.bar(ax=eixo, color="#1F3A5F")
    eixo.set_title(titulo)
    eixo.set_ylabel(rotulo_y)
    eixo.set_xlabel("")
    eixo.spines[["top", "right"]].set_visible(False)
    figura.tight_layout()
    figura.savefig(destino, dpi=150)
    plt.close(figura)


def principal() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    analisador.add_argument("--entrada", type=Path, default=Path("dados"))
    analisador.add_argument("--saida", type=Path, default=Path("dados"))
    argumentos = analisador.parse_args()
    pasta_figuras = argumentos.saida / "figuras"
    pasta_figuras.mkdir(parents=True, exist_ok=True)

    processos = carrega_processos(argumentos.entrada)
    print(f"Processos na amostra (após deduplicação): {len(processos)}")

    # 1. Volume por tribunal e por ano -------------------------------------
    volume_tribunal = processos.groupby("tribunal").size()
    volume_ano = processos.groupby("ano_ajuizamento").size()

    # 2. Duração média por tribunal ----------------------------------------
    duracao = processos.groupby("tribunal")["duracao_dias"].median()

    # 3. Desfechos ----------------------------------------------------------
    desfechos = (
        processos.groupby(["tribunal", "desfecho"]).size().unstack(fill_value=0)
    )
    com_sentenca = processos[processos["desfecho"] != "sem sentença identificada"]
    if len(com_sentenca):
        taxa_favoravel = (
            com_sentenca.assign(fav=com_sentenca["desfecho"].eq("favorável"))
            .groupby("tribunal")["fav"]
            .mean()
            .mul(100)
            .round(1)
        )
    else:
        taxa_favoravel = pd.Series(dtype=float)

    # 4. Frequência de movimentos (auditoria do classificador) --------------
    movimentos = frequencia_movimentos(argumentos.entrada)

    # Gravação ---------------------------------------------------------------
    processos.to_csv(argumentos.saida / "processos_bpc.csv", index=False)
    desfechos.to_csv(argumentos.saida / "metricas_desfechos.csv")
    movimentos.to_csv(argumentos.saida / "frequencia_movimentos.csv", index=False)

    resumo = pd.DataFrame(
        {
            "processos_amostra": volume_tribunal,
            "duracao_mediana_dias": duracao.round(0),
            "taxa_favoravel_pct": taxa_favoravel,
        }
    )
    resumo.to_csv(argumentos.saida / "metricas_resumo.csv")
    print("\n=== Resumo por tribunal ===")
    print(resumo.to_string())

    grafico_barras(
        volume_tribunal, "Processos de BPC na amostra, por TRF",
        "processos", pasta_figuras / "volume_por_trf.png",
    )
    grafico_barras(
        volume_ano.tail(15), "Ajuizamentos por ano (amostra)",
        "processos", pasta_figuras / "ajuizamentos_por_ano.png",
    )
    grafico_barras(
        duracao, "Duração mediana (ajuizamento → último movimento), por TRF",
        "dias", pasta_figuras / "duracao_por_trf.png",
    )
    if len(taxa_favoravel):
        grafico_barras(
            taxa_favoravel, "Taxa de sentenças favoráveis ao requerente, por TRF (%)",
            "%", pasta_figuras / "taxa_favoravel_por_trf.png",
        )

    print(f"\nArquivos gravados em {argumentos.saida}/ e {pasta_figuras}/")


if __name__ == "__main__":
    principal()

