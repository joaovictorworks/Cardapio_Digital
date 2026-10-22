from pathlib import Path

from database import inicializar_banco


def init_db():
    caminho_banco = Path(__file__).with_name('database.db')
    inicializar_banco(caminho_banco)
    print('Banco de dados inicializado/atualizado com sucesso.')


if __name__ == '__main__':
    init_db()
