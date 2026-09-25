from datetime import date

from anega2 import clima, sar


def test_plan_pre_y_post_dentro_de_ventana():
    fechas = [date(2024, 3, 1), date(2024, 3, 3), date(2024, 3, 13), date(2024, 3, 27)]
    assert sar.plan_escenas(fechas, date(2024, 3, 12), 12, 3) == (date(2024, 3, 3), date(2024, 3, 13))


def test_plan_sin_post_a_tiempo():
    fechas = [date(2024, 3, 3), date(2024, 3, 27)]
    assert sar.plan_escenas(fechas, date(2024, 3, 12), 12, 3) == (date(2024, 3, 3), None)


def test_plan_misma_fecha_es_post():
    assert sar.plan_escenas([date(2024, 3, 12)], date(2024, 3, 12), 12, 3) == (None, date(2024, 3, 12))


def test_resolve_events_auto_sin_clima(tmp_project, capsys):
    tmp_project.cfg["sar"]["eventos"] = "auto"
    assert clima.resolve_events(tmp_project) == []
    assert "correr la fase clima" in capsys.readouterr().out
