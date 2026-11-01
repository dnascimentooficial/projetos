from nordeste.site.formatacao import escala_auto, numero


def test_numero_formato_brasileiro():
    assert numero(1234.5, 1) == "1.234,5"
    assert numero(0.5032, 3) == "0,503"
    assert numero(1234567.891, 0) == "1.234.568"


def test_numero_nao_mostra_zero_negativo():
    assert numero(-0.04, 1) == "0,0"
    assert numero(-1.5, 1) == "-1,5"


def test_escala_auto():
    assert escala_auto(2186521) == "2,19 mi"
    assert escala_auto(403431) == "403 mil"
