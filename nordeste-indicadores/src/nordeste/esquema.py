"""Esquema da base: colunas, chave, vocabularios controlados e normalizacao."""

import pandas as pd

COLUNAS_BASE: list[str] = [
    "indicador_id", "subindicador", "etapa", "rede", "territorio_id",
    "ano", "valor", "tipo_dado", "serie_id", "coleta_id", "nota",
]

CHAVE_BASE: list[str] = [
    "indicador_id", "subindicador", "etapa", "rede", "territorio_id", "ano", "serie_id",
]

TIPOS_DADO: tuple[str, ...] = ("observado", "estimativa_oficial", "derivado", "indisponivel")

REDES: tuple[str, ...] = ("total", "publica", "privada", "federal", "estadual", "municipal")

COLUNAS_DERIVADOS: list[str] = [
    "indicador_id", "subindicador", "etapa", "rede", "metrica", "referencia",
    "territorio_id", "ano", "valor", "serie_id",
]

METRICAS: tuple[str, ...] = (
    "razao", "diferenca", "variacao_acumulada", "crescimento_relativo",
    "posicao_regioes", "dispersao_ufs",
)

# Colunas de texto que podem faltar na entrada; viram "" (nunca nulo).
_TEXTO_OPCIONAL = ["subindicador", "etapa", "rede", "nota"]
_TEXTO_OBRIGATORIO = ["indicador_id", "territorio_id", "tipo_dado", "serie_id", "coleta_id"]


def normalizar_base(df: pd.DataFrame) -> pd.DataFrame:
    """Devolve copia do df com as colunas de COLUNAS_BASE, na ordem, e tipos normalizados."""
    obrigatorias = [c for c in COLUNAS_BASE if c not in _TEXTO_OPCIONAL]
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        raise ValueError(f"colunas obrigatorias ausentes na base: {', '.join(faltando)}")

    out = df.copy()
    for coluna in _TEXTO_OPCIONAL:
        if coluna not in out.columns:
            out[coluna] = ""
    for coluna in _TEXTO_OPCIONAL + _TEXTO_OBRIGATORIO:
        out[coluna] = out[coluna].fillna("").astype(str)
    out["ano"] = out["ano"].astype(int)
    out["valor"] = pd.to_numeric(out["valor"]).astype(float)
    return out[COLUNAS_BASE].reset_index(drop=True)
