from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def abrir_banco(caminho_banco, habilitar_chaves_estrangeiras=False):
    conexao = conectar(caminho_banco, habilitar_chaves_estrangeiras)
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


def conectar(caminho_banco, habilitar_chaves_estrangeiras=False):
    conexao = sqlite3.connect(caminho_banco, timeout=10)
    conexao.row_factory = sqlite3.Row
    if habilitar_chaves_estrangeiras:
        conexao.execute('PRAGMA foreign_keys = ON')
    return conexao


def inicializar_banco(caminho_banco):
    caminho_schema = Path(__file__).with_name('banco.sql')
    conexao = conectar(caminho_banco)
    try:
        conexao.executescript(caminho_schema.read_text(encoding='utf-8'))
    finally:
        conexao.close()
