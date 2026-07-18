# Jurimetria do BPC/LOAS na Justiça Federal

Protótipo de pipeline em Python para **coleta automatizada e análise jurimétrica
de processos do Benefício de Prestação Continuada (BPC/LOAS)** nos cinco
Tribunais Regionais Federais, a partir da API Pública do DataJud (CNJ).

Projeto de estudo em métodos computacionais aplicados a dados jurídicos,
desenvolvido como complemento à minha formação (mestrado acadêmico em
Economia, UnB).

## O que o pipeline faz

1. **Coleta** (`src/coleta_datajud.py`) — consulta os índices públicos do
   DataJud dos TRF1–TRF5 (inclusive Juizados Especiais Federais), com
   paginação via `search_after`, recuo exponencial em erros transitórios e
   gravação em JSONL.
2. **Análise** (`src/analise_metricas.py`) — consolida os dados em `pandas` e
   calcula, por TRF, ano e grau: volume de ajuizamentos, duração mediana e
   desfecho das sentenças de mérito (favorável / desfavorável / acordo),
   classificado pelos códigos de movimento da Tabela Processual Unificada
   (SGT/CNJ), com salvaguarda por expressões regulares sobre os nomes dos
   movimentos. Gera CSVs e gráficos.

## Identificação dos assuntos de BPC

A maioria dos registros do DataJud traz apenas o **código** do assunto, sem o
nome. Os códigos relevantes foram identificados empiricamente, por agregação
de termos sobre o próprio índice público:

| Código TPU | Assunto | Observação |
|---|---|---|
| 6114 | Benefício Assistencial (Art. 203,V CF/88) | código-pai |
| 11946 | Deficiente | filho de 6114 |
| 11947 | Idoso | filho de 6114 |

Somados, esses três códigos correspondem a **≈ 1,1 milhão de processos apenas
no índice do TRF1** (consulta de julho/2026), o que confirma a escala da
judicialização descrita no *Justiça em Números 2024* (CNJ).

## Como executar

```bash
pip install -r requirements.txt

# amostra de demonstração: 500 processos por TRF
python src/coleta_datajud.py --max-por-tribunal 500 --saida dados/

# métricas, CSVs e gráficos
python src/analise_metricas.py --entrada dados/ --saida dados/
```

Saídas em `dados/`: `processos_bpc.csv`, `metricas_resumo.csv`,
`metricas_desfechos.csv`, `frequencia_movimentos.csv` e `figuras/*.png`.

## LGPD

A API pública do DataJud expõe somente **metadados processuais**
pseudonimizados (classe, assunto, órgão julgador, movimentos), sem nomes de
partes nem documentos pessoais. O pipeline não coleta dados pessoais.

## Limitações conhecidas

- O índice público reflete processos com movimentação recente e carga
  histórica heterogênea entre tribunais; a amostra de demonstração não é
  probabilística e as métricas servem para validar o pipeline, não para
  inferência sobre o universo.
- O classificador de desfechos cobre os movimentos de julgamento mais
  frequentes do SGT (219, 220, 221, 228, 466); a tabela
  `frequencia_movimentos.csv` permite auditá-lo e estendê-lo.
- A API não fornece o inteiro teor das decisões.

## Próximos passos (roteiro)

- Raspagem do inteiro teor nas bases de jurisprudência dos TRFs, para
  mineração de texto e classificação com LLMs executados localmente.
- Armazenamento estruturado + vetorial para recuperação de documentos.
- Desagregação por tipo de representação (Defensoria, advocacia privada,
  *jus postulandi*) e cruzamento com registros administrativos (CadÚnico).
