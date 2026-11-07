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
        colunas_pedido = {
            coluna['name']
            for coluna in conexao.execute('PRAGMA table_info(pedido)').fetchall()
        }
        if 'token_acompanhamento' not in colunas_pedido:
            conexao.execute(
                'ALTER TABLE pedido ADD COLUMN token_acompanhamento TEXT'
            )
        conexao.execute(
            '''CREATE UNIQUE INDEX IF NOT EXISTS idx_pedido_token_acompanhamento
               ON pedido(token_acompanhamento)
               WHERE token_acompanhamento IS NOT NULL'''
        )
        conexao.commit()
    finally:
        conexao.close()
