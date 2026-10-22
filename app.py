import math
import os
from pathlib import Path
import secrets
import uuid

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from database import abrir_banco
from orders import orders

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config['DATABASE'] = Path(app.root_path) / 'database.db'
app.config['UPLOAD_FOLDER'] = Path(app.root_path) / 'static' / 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.register_blueprint(orders)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)


def conexao():
    return abrir_banco(app.config['DATABASE'])


def extensao_permitida(nome_arquivo):
    return '.' in nome_arquivo and nome_arquivo.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def salvar_imagem(arquivo, prefixo='imagem'):
    if not arquivo or not arquivo.filename:
        return None

    nome_original = secure_filename(arquivo.filename)
    if not extensao_permitida(nome_original):
        raise ValueError('Formato de imagem não permitido. Use PNG, JPG, JPEG, GIF ou WEBP.')

    extensao = nome_original.rsplit('.', 1)[1].lower()
    nome = f'{prefixo}_{uuid.uuid4().hex}.{extensao}'
    arquivo.save(app.config['UPLOAD_FOLDER'] / nome)
    return f'uploads/{nome}'


def excluir_imagem(caminho):
    if not caminho or not caminho.startswith('uploads/'):
        return
    arquivo = Path(app.root_path) / 'static' / caminho
    if arquivo.exists() and arquivo.is_file():
        arquivo.unlink()

@app.route('/login_usuario', methods=['GET', 'POST'])
def loginUsuario():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')

        with conexao() as conn:
            usuario = conn.execute(
                'SELECT id, nome, senha, ativo FROM usuario WHERE nome = ?',
                (nome,),
            ).fetchone()

        usuario_ativo = usuario and str(usuario['ativo']).strip().lower() in {
            '1', 'true', 'ativo',
        }
        if not usuario_ativo or not check_password_hash(usuario['senha'], senha):
            flash('Nome de usuário ou senha inválidos.', 'danger')
            return _renderizar_login()

        session.clear()
        session['usuario_id'] = usuario['id']
        session['usuario_nome'] = usuario['nome']
        return redirect(url_for('index'))

    return _renderizar_login()


def _renderizar_login():
    with conexao() as conn:
        primeiro_acesso = conn.execute(
            'SELECT 1 FROM usuario LIMIT 1'
        ).fetchone() is None
    return render_template(
        'admin/login_usuario.html',
        primeiro_acesso=primeiro_acesso,
    )


@app.before_request
def exigir_login():
    endpoints_publicos = {
        'static',
        'inicio_publico',
        'loginUsuario',
        'catalogo',
        'viewer_categoria',
        'viewer_produto',
        'orders.criar_pedido',
    }
    if request.endpoint == 'cadastrarUsuario' and 'usuario_id' not in session:
        with conexao() as conn:
            primeiro_acesso = conn.execute(
                'SELECT 1 FROM usuario LIMIT 1'
            ).fetchone() is None
        if primeiro_acesso:
            return None

    if request.endpoint not in endpoints_publicos and 'usuario_id' not in session:
        flash('Faça login para acessar essa página.', 'warning')
        return redirect(url_for('loginUsuario'))


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'success')
    return redirect(url_for('loginUsuario'))

@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastrarUsuario():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not nome or not senha:
            flash('Informe o nome e a senha do usuário.', 'danger')
            return render_template('admin/cadastrar_usuario.html')

        if senha != confirmar_senha:
            flash('As senhas não conferem.', 'danger')
            return render_template('admin/cadastrar_usuario.html')

        with conexao() as conn:
            if conn.execute('SELECT 1 FROM usuario WHERE nome = ?', (nome,)).fetchone():
                flash('Já existe um usuário com esse nome.', 'danger')
                return render_template('admin/cadastrar_usuario.html')

            conn.execute(
                'INSERT INTO usuario (nome, senha, ativo) VALUES (?, ?, ?)',
                (nome, generate_password_hash(senha), 'True'),
            )
            conn.commit()

        flash('Usuário cadastrado com sucesso.', 'success')

        return redirect(url_for('loginUsuario'))

    return render_template('admin/cadastrar_usuario.html')

@app.route('/admin')
def index():
    with conexao() as conn:
        total_pedidos_novos = conn.execute(
            "SELECT COUNT(*) FROM pedido WHERE status = 'novo'"
        ).fetchone()[0]
    return render_template(
        'admin/index.html',
        total_pedidos_novos=total_pedidos_novos,
    )


@app.route('/')
def inicio_publico():
    return redirect(url_for('viewer_categoria'))


@app.route('/listar_categorias')
def listarCategoria():
    with conexao() as conn:
        categorias = conn.execute('SELECT * FROM categoria ORDER BY id DESC').fetchall()
    return render_template('admin/listar_categoria.html', categorias=categorias)


@app.route('/cadastrar_categorias', methods=['GET', 'POST'])
def cadastrarCategoria():
    if request.method == 'POST':
        nome_categoria = request.form.get('nome_categoria', '').strip()
        descricao = request.form.get('descricao', '').strip()
        ativo = request.form.get('ativo', 'False')
        imagem = request.files.get('imagem')

        if not nome_categoria:
            flash('Informe o nome da categoria.', 'danger')
            return render_template('admin/cadastrar_categoria.html')

        try:
            caminho_imagem = salvar_imagem(imagem, 'categoria')
        except ValueError as erro:
            flash(str(erro), 'danger')
            return render_template('admin/cadastrar_categoria.html')

        with conexao() as conn:
            conn.execute(
                '''INSERT INTO categoria (nome, descricao, ativo, img)
                   VALUES (?, ?, ?, ?)''',
                (nome_categoria, descricao, ativo, caminho_imagem),
            )
            conn.commit()

        flash('Categoria cadastrada com sucesso.', 'success')
        return redirect(url_for('listarCategoria'))

    return render_template('admin/cadastrar_categoria.html')


@app.route('/editarcategoria/<int:id>', methods=['GET', 'POST'])
def editarCategoria(id):
    with conexao() as conn:
        categoria = conn.execute('SELECT * FROM categoria WHERE id = ?', (id,)).fetchone()

    if categoria is None:
        flash('Categoria não encontrada.', 'danger')
        return redirect(url_for('listarCategoria'))

    if request.method == 'POST':
        nome_categoria = request.form.get('nome_categoria', '').strip()
        descricao = request.form.get('descricao', '').strip()
        ativo = request.form.get('ativo', 'False')
        imagem = request.files.get('imagem')
        caminho_imagem = categoria['img']

        if not nome_categoria:
            flash('Informe o nome da categoria.', 'danger')
            return render_template('admin/editar_categoria.html', categoria=categoria)

        if imagem and imagem.filename:
            try:
                novo_caminho = salvar_imagem(imagem, f'categoria_{id}')
            except ValueError as erro:
                flash(str(erro), 'danger')
                return render_template('admin/editar_categoria.html', categoria=categoria)

            excluir_imagem(caminho_imagem)
            caminho_imagem = novo_caminho

        with conexao() as conn:
            conn.execute(
                '''UPDATE categoria
                   SET nome = ?, descricao = ?, ativo = ?, img = ?
                   WHERE id = ?''',
                (nome_categoria, descricao, ativo, caminho_imagem, id),
            )
            conn.commit()

        flash('Categoria atualizada com sucesso.', 'success')
        return redirect(url_for('listarCategoria'))

    return render_template('admin/editar_categoria.html', categoria=categoria)


@app.route('/excluir_categoria/<int:id>', methods=['GET', 'POST'])
def excluirCategoria(id):
    with conexao() as conn:
        categoria = conn.execute('SELECT * FROM categoria WHERE id = ?', (id,)).fetchone()

    if categoria is None:
        flash('Categoria não encontrada.', 'danger')
        return redirect(url_for('listarCategoria'))

    if request.method == 'POST':
        with conexao() as conn:
            conn.execute('DELETE FROM categoria WHERE id = ?', (id,))
            conn.commit()
        excluir_imagem(categoria['img'])
        flash('Categoria excluída com sucesso.', 'success')
        return redirect(url_for('listarCategoria'))

    return render_template('admin/excluir_categoria.html', categoria=categoria)


@app.route('/listar_produtos')
def listarProduto():
    with conexao() as conn:
        produtos = conn.execute(
            '''SELECT produto.*, categoria.nome AS categoria_nome
               FROM produto
               LEFT JOIN categoria ON categoria.id = produto.id_categoria
               ORDER BY produto.id DESC'''
        ).fetchall()
    return render_template('admin/listar_produto.html', produtos=produtos)

@app.route('/cadastrar_produtos', methods=['GET', 'POST'])
def cadastrarProduto():
    with conexao() as conn:
        categorias = conn.execute(
            'SELECT id, nome FROM categoria ORDER BY nome'
        ).fetchall()

        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            preco_texto = request.form.get('preco', '').strip().replace(',', '.')
            ativo = request.form.get('ativo', '')
            id_categoria_texto = request.form.get('id_categoria', '')

            try:
                preco = float(preco_texto)
            except ValueError:
                preco = None

            try:
                id_categoria = int(id_categoria_texto)
            except ValueError:
                id_categoria = None

            categoria_valida = (
                conn.execute(
                    'SELECT id FROM categoria WHERE id = ?', (id_categoria,)
                ).fetchone()
                if id_categoria is not None
                else None
            )

            if not nome:
                erro = 'Informe o nome do produto.'
            elif preco is None or not math.isfinite(preco) or preco < 0:
                erro = 'Informe um preço válido.'
            elif ativo not in ('True', 'False'):
                erro = 'Selecione um status válido.'
            elif categoria_valida is None:
                erro = 'Selecione uma categoria válida.'
            else:
                imagem = request.files.get('imagem')
                try:
                    caminho_imagem = salvar_imagem(imagem, 'produto')
                except ValueError as erro:
                    flash(str(erro), 'danger')
                    return render_template(
                        'admin/cadastrar_produto.html',
                        categorias=categorias,
                    )

                conn.execute(
                    '''INSERT INTO produto (nome, preco, ativo, img, id_categoria)
                       VALUES (?, ?, ?, ?, ?)''',
                    (nome, preco, ativo, caminho_imagem, id_categoria),
                )
                conn.commit()
                flash('Produto cadastrado com sucesso.', 'success')
                return redirect(url_for('listarProduto'))

            return render_template(
                'admin/cadastrar_produto.html',
                categorias=categorias,
                erro=erro,
            )

    return render_template(
        'admin/cadastrar_produto.html',
        categorias=categorias,
    )


@app.route('/excluir_produto/<int:id>', methods=['GET', 'POST'])
def excluirProduto(id):
    with conexao() as conn:
        produto = conn.execute('SELECT * FROM produto WHERE id = ?', (id,)).fetchone()

    if produto is None:
        flash('Produto não encontrada.', 'danger')
        return redirect(url_for('listarProduto'))

    if request.method == 'POST':
        with conexao() as conn:
            conn.execute('DELETE FROM produto WHERE id = ?', (id,))
            conn.commit()
        excluir_imagem(produto['img'])
        flash('Produto excluída com sucesso.', 'success')
        return redirect(url_for('listarProduto'))

    return render_template('admin/excluir_produto.html', produto=produto)

@app.route('/catalogo')
@app.route('/site/viewer_categoria')
def viewer_categoria():
    with conexao() as conn:
        linhas = conn.execute(
            '''
            SELECT
                c.id AS categoria_id,
                c.nome AS categoria_nome,
                c.descricao AS categoria_descricao,
                c.img AS categoria_img,
                p.id AS produto_id,
                p.nome AS produto_nome,
                p.preco AS produto_preco,
                p.img AS produto_img
            FROM categoria AS c
            LEFT JOIN produto AS p
                ON p.id_categoria = c.id
                AND p.ativo = 'True'
            WHERE c.ativo = 'True'
            ORDER BY c.nome, p.nome
            '''
        ).fetchall()

    categorias_por_id = {}

    for linha in linhas:
        categoria_id = linha['categoria_id']

        if categoria_id not in categorias_por_id:
            categorias_por_id[categoria_id] = {
                'nome': linha['categoria_nome'],
                'descricao': linha['categoria_descricao'],
                'img': linha['categoria_img'],
                'produtos': [],
            }

        if linha['produto_id'] is not None:
            categorias_por_id[categoria_id]['produtos'].append({
                'id': linha['produto_id'],
                'nome': linha['produto_nome'],
                'preco': linha['produto_preco'],
                'img': linha['produto_img'],
            })

    return render_template(
        'site/viewer_categoria.html',
        categorias=list(categorias_por_id.values()),
    )
@app.route('/site/viewer_produto', methods=['GET'])
def viewer_produto():

    return redirect(url_for('viewer_categoria'))

@app.route('/listar_usuarios')
def listarUsuarios():
    with conexao() as conn:
        usuarios = conn.execute('SELECT * FROM usuario ORDER BY id DESC').fetchall()
    return render_template('admin/listar_usuario.html', usuarios=usuarios)

@app.route('/editar_usuario/<int:id>', methods=['GET', 'POST'])
def editarUsuario(id):
    with conexao() as conn:
        usuario = conn.execute('SELECT * FROM usuario WHERE id = ?', (id,)).fetchone()

    if usuario is None:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('listarUsuario'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha')
        confirmar_senha = request.form.get('confirmar_senha')
        ativo = request.form.get('ativo', 'False')

        if not nome:
            flash('Informe o nome do usuário.', 'danger')
            return render_template('admin/editar_usuario.html', usuario=usuario)

        if senha != confirmar_senha:
            flash('As senhas não conferem.', 'danger')
            return render_template('admin/editar_usuario.html', usuario=usuario)

        with conexao() as conn:
            if conn.execute('SELECT 1 FROM usuario WHERE nome = ? AND id <> ?', (nome, id)).fetchone():
                flash('Já existe um usuário com esse nome.', 'danger')
                return render_template('admin/editar_usuario.html', usuario=usuario)

            if senha:
                conn.execute(
                    'UPDATE usuario SET nome = ?, senha = ?, ativo = ? WHERE id = ?',
                    (nome, generate_password_hash(senha), ativo, id),
                )
            else:
                conn.execute(
                    'UPDATE usuario SET nome = ?, ativo = ? WHERE id = ?',
                    (nome, ativo, id),
                )
            conn.commit()

        flash('Usuário atualizado com sucesso.', 'success')
        return redirect(url_for('listarUsuario'))

    return render_template('admin/editar_usuario.html', usuario=usuario)


@app.route('/excluir_usuario/<int:id>', methods=['GET', 'POST'])
def excluirUsuario(id):
    with conexao() as conn:
        usuario = conn.execute('SELECT id, nome FROM usuario WHERE id = ?', (id,)).fetchone()

    if usuario is None:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('listarUsuario'))

    if request.method == 'POST':
        with conexao() as conn:
            conn.execute('DELETE FROM usuario WHERE id = ?', (id,))
            conn.commit()
        flash('Usuário excluído com sucesso.', 'success')
        return redirect(url_for('listarUsuario'))

    return render_template('admin/excluir_usuario.html', usuario=usuario)

if __name__ == '__main__':
    app.run(debug=True, port=5005)