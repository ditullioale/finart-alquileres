"""Fase 3.1 — las suites históricas corren dentro de pytest, sin reescribirlas.

Cada suite ya es completa y rápida; la ejecutamos como un subproceso aislado (igual
que en CI) y pedimos que termine en 0. Así `pytest` corre TODO (QA + aislamiento +
facturador + E2E) con un solo comando, sin perder las 200+ verificaciones existentes.
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _correr(script):
    env = dict(os.environ, TESTING="1")
    r = subprocess.run([sys.executable, script], cwd=str(ROOT), env=env,
                       capture_output=True, text=True)
    # Si falla, mostramos la cola de la salida para diagnosticar.
    assert r.returncode == 0, f"{script} falló:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}"


@pytest.mark.parametrize("script", [
    "tests_qa.py",
    "test_aislamiento.py",
    "test_facturador.py",
])
def test_suite_historica(script):
    _correr(script)
