"""Fixtures comunes: proyecto temporal mínimo (sin red ni datos pesados)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import anega2.project as project_mod

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Proyecto 'ejemplo' en un PROJECTS_DIR temporal, con el lote.kml del ejemplo público."""
    monkeypatch.setattr(project_mod, "PROJECTS_DIR", tmp_path)
    d = tmp_path / "ejemplo"; d.mkdir()
    shutil.copy(REPO / "projects/ejemplo-bajo-giles/lote.kml", d / "lote.kml")
    (d / "project.yml").write_text("nombre: ejemplo\ntitulo: Ejemplo\nkml: lote.kml\n")
    return project_mod.Project.load("ejemplo", yes=True)
