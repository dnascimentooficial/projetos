"""Erros compartilhados pelos coletores."""


class ErroColeta(RuntimeError):
    """Falha ao coletar uma serie (rede, fixture ausente ou serie nao verificada)."""
