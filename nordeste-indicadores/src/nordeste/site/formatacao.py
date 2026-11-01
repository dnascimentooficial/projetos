"""Formatacao de numeros no padrao brasileiro."""


def numero(valor: float, casas: int) -> str:
    """`1234.5, 1` -> `"1.234,5"`: ponto nos milhares, virgula nos decimais, sem zero negativo."""
    arredondado = round(valor, casas) or 0.0  # -0.0 e 0.0 viram 0.0: nunca "-0,0"
    texto = f"{arredondado:,.{casas}f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def escala_auto(valor: float) -> str:
    """Valor grande em escala curta: `2186521 -> "2,19 mi"` (de 1 milhao em diante), `403431 -> "403 mil"`."""
    if abs(valor) >= 1e6:
        return f"{numero(valor / 1e6, 2)} mi"
    return f"{numero(valor / 1e3, 0)} mil"
