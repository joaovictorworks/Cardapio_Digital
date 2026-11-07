import tempfile
import unittest
from pathlib import Path
import sqlite3

from app import app
from database import abrir_banco, inicializar_banco


class PedidoFluxoTests(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.banco_original = app.config['DATABASE']
        self.caminho_banco = Path(self.diretorio_temporario.name) / 'teste.db'
        app.config.update(TESTING=True, DATABASE=self.caminho_banco)
        inicializar_banco(self.caminho_banco)

        with abrir_banco(self.caminho_banco) as conexao:
            conexao.execute(
                "INSERT INTO categoria (nome, ativo) VALUES ('Lanches', 'True')"
            )
            conexao.execute(
                '''INSERT INTO produto (nome, preco, ativo, id_categoria)
                   VALUES ('X-Burger', 12.50, 'True', 1)'''
            )
            conexao.execute(
                '''INSERT INTO usuario (nome, senha, ativo)
                   VALUES ('admin', 'hash', 'True')'''
            )

        self.cliente = app.test_client()

    def tearDown(self):
        app.config['DATABASE'] = self.banco_original
        self.diretorio_temporario.cleanup()

    def test_cliente_cria_pedido_com_preco_do_banco(self):
        resposta = self.cliente.post(
            '/pedidos',
            data={
                'cliente_nome': 'Ana',
                'cliente_telefone': '11999990000',
                'quantidade_1': '2',
                'preco_1': '0.01',
            },
        )

        self.assertEqual(resposta.status_code, 302)
        with abrir_banco(self.caminho_banco) as conexao:
            pedido = conexao.execute(
                'SELECT cliente_nome, total_centavos, status FROM pedido'
            ).fetchone()
            item = conexao.execute(
                '''SELECT produto_nome, quantidade, preco_unitario_centavos,
                          subtotal_centavos FROM item_pedido'''
            ).fetchone()

        self.assertEqual(tuple(pedido), ('Ana', 2500, 'novo'))
        self.assertEqual(tuple(item), ('X-Burger', 2, 1250, 2500))

    def test_cliente_acompanha_status_com_codigo_secreto(self):
        self.cliente.post(
            '/pedidos',
            data={'cliente_nome': 'Ana', 'quantidade_1': '1'},
        )
        with self.cliente.session_transaction() as sessao:
            token = sessao['pedido_acompanhamento']

        resposta = self.cliente.get('/pedido/status')
        self.assertEqual(resposta.json['status'], 'novo')
        self.assertTrue(resposta.json['acompanhamento'])

        with self.cliente.session_transaction() as sessao:
            sessao['usuario_id'] = 1
            sessao['usuario_nome'] = 'admin'
        self.cliente.post(
            '/admin/pedidos/1/status',
            data={'status': 'preparando'},
        )
        resposta = self.cliente.get('/pedido/status')
        self.assertEqual(resposta.json['status'], 'preparando')
        self.assertEqual(len(token), 43)

        outro_cliente = app.test_client()
        resposta = outro_cliente.get('/pedido/status')
        self.assertEqual(resposta.json, {'acompanhamento': False})
        outro_cliente.post(
            '/pedido/acompanhamento',
            data={'token_acompanhamento': token},
        )
        resposta = outro_cliente.get('/pedido/status')
        self.assertEqual(resposta.json['status'], 'preparando')

    def test_codigo_de_acompanhamento_invalido_nao_revela_pedido(self):
        resposta = self.cliente.post(
            '/pedido/acompanhamento',
            data={'token_acompanhamento': 'codigo-invalido'},
            follow_redirects=True,
        )
        self.assertIn('Código de acompanhamento não encontrado'.encode(), resposta.data)
        self.assertEqual(
            self.cliente.get('/pedido/status').json,
            {'acompanhamento': False},
        )

    def test_catalogo_publico_e_qrcode_administrativo_renderizam(self):
        resposta = self.cliente.get('/catalogo')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'X-Burger', resposta.data)
        self.assertIn(b'quantidade_1', resposta.data)

        with self.cliente.session_transaction() as sessao:
            sessao['usuario_id'] = 1
            sessao['usuario_nome'] = 'admin'
        resposta = self.cliente.get('/admin/qrcode')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'qrcode.min.js', resposta.data)

    def test_catalogo_renderiza_mensagem_flash_sem_endpoint_de_status(self):
        resposta = self.cliente.post(
            '/pedidos',
            data={'cliente_nome': 'Ana'},
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Escolha pelo menos um item'.encode(), resposta.data)

    def test_migracao_repetida_preserva_catalogo(self):
        inicializar_banco(self.caminho_banco)
        with abrir_banco(self.caminho_banco) as conexao:
            quantidade = conexao.execute(
                'SELECT COUNT(*) FROM produto WHERE nome = ?',
                ('X-Burger',),
            ).fetchone()[0]
        self.assertEqual(quantidade, 1)

    def test_migracao_adiciona_codigo_a_banco_existente(self):
        caminho_legado = Path(self.diretorio_temporario.name) / 'legado.db'
        conexao = sqlite3.connect(caminho_legado)
        conexao.execute(
            '''CREATE TABLE pedido (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   cliente_nome TEXT NOT NULL,
                   cliente_telefone TEXT,
                   observacoes TEXT,
                   status TEXT NOT NULL DEFAULT 'novo',
                   total_centavos INTEGER NOT NULL,
                   criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                   atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )'''
        )
        conexao.commit()
        conexao.close()

        inicializar_banco(caminho_legado)
        with abrir_banco(caminho_legado) as conexao:
            colunas = {
                coluna['name']
                for coluna in conexao.execute('PRAGMA table_info(pedido)')
            }
        self.assertIn('token_acompanhamento', colunas)

    def test_rejeita_quantidade_invalida_sem_gravar_pedido(self):
        resposta = self.cliente.post(
            '/pedidos',
            data={'cliente_nome': 'Ana', 'quantidade_1': '100'},
        )

        self.assertEqual(resposta.status_code, 302)
        with abrir_banco(self.caminho_banco) as conexao:
            total = conexao.execute('SELECT COUNT(*) FROM pedido').fetchone()[0]
        self.assertEqual(total, 0)

    def test_nao_aceita_produto_que_ficou_inativo(self):
        with abrir_banco(self.caminho_banco) as conexao:
            conexao.execute("UPDATE produto SET ativo = 'False' WHERE id = 1")

        resposta = self.cliente.post(
            '/pedidos',
            data={'cliente_nome': 'Ana', 'quantidade_1': '1'},
        )

        self.assertEqual(resposta.status_code, 302)
        with abrir_banco(self.caminho_banco) as conexao:
            total = conexao.execute('SELECT COUNT(*) FROM pedido').fetchone()[0]
        self.assertEqual(total, 0)

    def test_painel_exige_login_e_permite_atualizar_status(self):
        resposta = self.cliente.get('/admin/pedidos')
        self.assertEqual(resposta.status_code, 302)

        self.cliente.post(
            '/pedidos',
            data={'cliente_nome': 'Ana', 'quantidade_1': '1'},
        )
        with self.cliente.session_transaction() as sessao:
            sessao['usuario_id'] = 1
            sessao['usuario_nome'] = 'admin'

        resposta = self.cliente.get('/admin/pedidos')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'Ana', resposta.data)
        resposta = self.cliente.get('/admin/pedidos/novos.json')
        self.assertEqual(resposta.json, {'novos': 1})

        resposta = self.cliente.post(
            '/admin/pedidos/1/status',
            data={'status': 'preparando'},
        )
        self.assertEqual(resposta.status_code, 302)
        with abrir_banco(self.caminho_banco) as conexao:
            status = conexao.execute(
                'SELECT status FROM pedido WHERE id = 1'
            ).fetchone()[0]
        self.assertEqual(status, 'preparando')
        resposta = self.cliente.get('/admin/pedidos/novos.json')
        self.assertEqual(resposta.json, {'novos': 0})

    def test_painel_pagina_pedidos_e_navega_entre_paginas(self):
        with abrir_banco(self.caminho_banco) as conexao:
            conexao.executemany(
                '''INSERT INTO pedido (cliente_nome, total_centavos)
                   VALUES (?, 0)''',
                [(f'Cliente {numero}',) for numero in range(11)],
            )
        with self.cliente.session_transaction() as sessao:
            sessao['usuario_id'] = 1
            sessao['usuario_nome'] = 'admin'

        primeira_pagina = self.cliente.get('/admin/pedidos')
        self.assertEqual(primeira_pagina.status_code, 200)
        self.assertIn(b'Cliente 10', primeira_pagina.data)
        self.assertNotIn(b'Cliente 0</h2>', primeira_pagina.data)
        self.assertIn(b'/admin/pedidos?page=2', primeira_pagina.data)

        segunda_pagina = self.cliente.get('/admin/pedidos?page=2')
        self.assertEqual(segunda_pagina.status_code, 200)
        self.assertIn(b'Cliente 0</h2>', segunda_pagina.data)
        self.assertIn(b'/admin/pedidos?page=1', segunda_pagina.data)

    def test_cadastro_de_usuario_exige_login_apos_primeiro_acesso(self):
        resposta = self.cliente.get('/cadastrar_usuario')
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.location, '/login_usuario')

    def test_primeira_conta_administrativa_pode_ser_criada(self):
        with abrir_banco(self.caminho_banco) as conexao:
            conexao.execute('DELETE FROM usuario')

        resposta = self.cliente.get('/login_usuario')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Criar a primeira conta administrativa'.encode(), resposta.data)

        resposta = self.cliente.post(
            '/cadastrar_usuario',
            data={
                'nome': 'primeiro-admin',
                'senha': 'senha-segura',
                'confirmar_senha': 'senha-segura',
            },
        )
        self.assertEqual(resposta.status_code, 302)
        with abrir_banco(self.caminho_banco) as conexao:
            nome = conexao.execute(
                'SELECT nome FROM usuario'
            ).fetchone()[0]
        self.assertEqual(nome, 'primeiro-admin')

if __name__ == '__main__':
    unittest.main()
