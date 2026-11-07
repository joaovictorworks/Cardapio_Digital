from decimal import Decimal, ROUND_HALF_UP
import secrets

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from database import abrir_banco


orders = Blueprint('orders', __name__)
PEDIDOS_POR_PAGINA = 10
STATUS_PEDIDO = {
    'novo': 'Novo',
    'aceito': 'Aceito',
    'preparando': 'Em preparo',
    'pronto': 'Pronto',
    'concluido': 'Concluído',
    'cancelado': 'Cancelado',
}


class Paginacao:
    def __init__(self, itens, pagina, por_pagina, total):
        self.itens = itens
        self.page = pagina
        self.per_page = por_pagina
        self.total = total
        self.pages = max(1, (total + por_pagina - 1) // por_pagina)

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def __iter__(self):
        return iter(self.itens)

    def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
        ultima_pagina = 0
        for numero in range(1, self.pages + 1):
            if (
                numero <= left_edge
                or self.page - left_current - 1 < numero < self.page + right_current
                or numero > self.pages - right_edge
            ):
                if ultima_pagina + 1 != numero:
                    yield None
                yield numero
                ultima_pagina = numero


def _banco():
    return abrir_banco(
        current_app.config['DATABASE'],
        habilitar_chaves_estrangeiras=True,
    )


def _centavos(valor):
    return int(
        (Decimal(str(valor)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    )


def _ler_itens_pedido(formulario):
    itens = []
    try:
        for campo, valor in formulario.items():
            if not campo.startswith('quantidade_'):
                continue
            produto_id = int(campo.removeprefix('quantidade_'))
            quantidade = int(valor)
            if produto_id < 1 or quantidade < 0 or quantidade > 99:
                raise ValueError
            if quantidade:
                itens.append((produto_id, quantidade))
    except ValueError as erro:
        raise ValueError('Confira as quantidades selecionadas e tente novamente.') from erro

    if not itens:
        raise ValueError('Escolha pelo menos um item para fazer o pedido.')
    if len(itens) > 100:
        raise ValueError('O pedido ultrapassou o limite de itens diferentes.')
    return itens


@orders.route('/pedidos', methods=['POST'])
def criar_pedido():
    nome = request.form.get('cliente_nome', '').strip()
    telefone = request.form.get('cliente_telefone', '').strip()
    observacoes = request.form.get('observacoes', '').strip()

    if not nome or len(nome) > 100:
        flash('Informe seu nome (até 100 caracteres) para continuar.', 'danger')
        return redirect(url_for('viewer_categoria'))
    if len(telefone) > 30 or len(observacoes) > 500:
        flash('O telefone ou as observações excedem o limite permitido.', 'danger')
        return redirect(url_for('viewer_categoria'))

    try:
        itens_solicitados = _ler_itens_pedido(request.form)
    except ValueError as erro:
        flash(str(erro), 'danger')
        return redirect(url_for('viewer_categoria'))

    ids_produtos = [produto_id for produto_id, _ in itens_solicitados]
    placeholders = ','.join('?' for _ in ids_produtos)

    try:
        with _banco() as conexao:
            conexao.execute('BEGIN IMMEDIATE')
            produtos = conexao.execute(
                f'''SELECT p.id, p.nome, p.preco
                    FROM produto AS p
                    JOIN categoria AS c ON c.id = p.id_categoria
                    WHERE p.id IN ({placeholders})
                      AND p.ativo = 'True'
                      AND c.ativo = 'True'
                      AND p.preco IS NOT NULL
                      AND p.preco >= 0 ''',
                ids_produtos,
            ).fetchall()
            produtos_por_id = {produto['id']: produto for produto in produtos}
            if len(produtos_por_id) != len(ids_produtos):
                raise ValueError(
                    'Um ou mais produtos não estão mais disponíveis. Atualize o cardápio.'
                )

            itens = []
            total_centavos = 0
            for produto_id, quantidade in itens_solicitados:
                produto = produtos_por_id[produto_id]
                preco_centavos = _centavos(produto['preco'])
                subtotal_centavos = preco_centavos * quantidade
                total_centavos += subtotal_centavos
                itens.append(
                    (produto_id, produto['nome'], quantidade, preco_centavos, subtotal_centavos)
                )

            cursor = conexao.execute(
                '''INSERT INTO pedido
                   (cliente_nome, cliente_telefone, observacoes, status,
                    total_centavos, token_acompanhamento)
                   VALUES (?, ?, ?, 'novo', ?, ?)''',
                (
                    nome,
                    telefone or None,
                    observacoes or None,
                    total_centavos,
                    secrets.token_urlsafe(32),
                ),
            )
            pedido_id = cursor.lastrowid
            token_acompanhamento = conexao.execute(
                'SELECT token_acompanhamento FROM pedido WHERE id = ?',
                (pedido_id,),
            ).fetchone()['token_acompanhamento']
            conexao.executemany(
                '''INSERT INTO item_pedido
                   (pedido_id, produto_id, produto_nome, quantidade,
                    preco_unitario_centavos, subtotal_centavos)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                [
                    (pedido_id, produto_id, produto_nome, quantidade, preco, subtotal)
                    for produto_id, produto_nome, quantidade, preco, subtotal in itens
                ],
            )
            conexao.commit()
    except ValueError as erro:
        flash(str(erro), 'danger')
        return redirect(url_for('viewer_categoria'))

    session['pedido_acompanhamento'] = token_acompanhamento
    flash(
        f'Pedido #{pedido_id} enviado! Guarde seu código de acompanhamento: '
        f'{token_acompanhamento}',
        'success',
    )
    return redirect(url_for('viewer_categoria'))


@orders.route('/pedido/acompanhamento', methods=['POST'])
def acompanhar_pedido():
    token = request.form.get('token_acompanhamento', '').strip()
    if not token or len(token) > 128:
        flash('Informe um código de acompanhamento válido.', 'danger')
        return redirect(url_for('viewer_categoria'))

    with _banco() as conexao:
        pedido = conexao.execute(
            'SELECT 1 FROM pedido WHERE token_acompanhamento = ?',
            (token,),
        ).fetchone()

    if pedido is None:
        flash('Código de acompanhamento não encontrado.', 'danger')
        return redirect(url_for('viewer_categoria'))

    session['pedido_acompanhamento'] = token
    flash('Pedido localizado. O status será atualizado automaticamente.', 'success')
    return redirect(url_for('viewer_categoria'))


@orders.route('/pedido/status')
def consultar_status_cliente():
    token = session.get('pedido_acompanhamento')
    if not token:
        return jsonify(acompanhamento=False)

    with _banco() as conexao:
        pedido = conexao.execute(
            '''SELECT id, status, atualizado_em
               FROM pedido WHERE token_acompanhamento = ?''',
            (token,),
        ).fetchone()

    if pedido is None:
        session.pop('pedido_acompanhamento', None)
        return jsonify(acompanhamento=False)

    return jsonify(
        acompanhamento=True,
        pedido_id=pedido['id'],
        status=pedido['status'],
        status_texto=STATUS_PEDIDO[pedido['status']],
        atualizado_em=pedido['atualizado_em'],
    )


@orders.route('/admin/pedidos')
def listar_pedidos():
    with _banco() as conexao:
        total = conexao.execute('SELECT COUNT(*) FROM pedido').fetchone()[0]
        paginas = max(1, (total + PEDIDOS_POR_PAGINA - 1) // PEDIDOS_POR_PAGINA)
        pagina = min(max(request.args.get('page', 1, type=int), 1), paginas)
        pedidos = conexao.execute(
            '''SELECT id, cliente_nome, cliente_telefone, observacoes,
                      status, total_centavos, criado_em
               FROM pedido
               ORDER BY CASE status WHEN 'novo' THEN 0 ELSE 1 END, id DESC
               LIMIT ? OFFSET ?''',
            (PEDIDOS_POR_PAGINA, (pagina - 1) * PEDIDOS_POR_PAGINA),
        ).fetchall()
        ids_pedidos = [pedido['id'] for pedido in pedidos]
        if ids_pedidos:
            placeholders = ','.join('?' for _ in ids_pedidos)
            itens = conexao.execute(
                f'''SELECT pedido_id, produto_nome, quantidade,
                           preco_unitario_centavos, subtotal_centavos
                    FROM item_pedido
                    WHERE pedido_id IN ({placeholders})
                    ORDER BY id''',
                ids_pedidos,
            ).fetchall()
        else:
            itens = []

    itens_por_pedido = {pedido_id: () for pedido_id in ids_pedidos}
    for item in itens:
        itens_por_pedido[item['pedido_id']] += (item,)

    paginacao = Paginacao(pedidos, pagina, PEDIDOS_POR_PAGINA, total)
    return render_template(
        'admin/pedidos.html',
        pedidos=paginacao,
        itens_por_pedido=itens_por_pedido,
        status_pedido=STATUS_PEDIDO,
    )
@orders.route('/admin/pedidos/<int:pedido_id>/status', methods=['POST'])
def atualizar_status(pedido_id):
    status = request.form.get('status', '')
    if status not in STATUS_PEDIDO:
        flash('Selecione um status válido para o pedido.', 'danger')
        return redirect(url_for('orders.listar_pedidos'))

    with _banco() as conexao:
        resultado = conexao.execute(
            '''UPDATE pedido SET status = ?, atualizado_em = CURRENT_TIMESTAMP
               WHERE id = ?''',
            (status, pedido_id),
        )
        conexao.commit()

    if resultado.rowcount == 0:
        flash('Pedido não encontrado.', 'danger')
    else:
        flash(f'Status do pedido #{pedido_id} atualizado.', 'success')
    return redirect(url_for('orders.listar_pedidos'))


@orders.route('/admin/pedidos/novos.json')
def contar_pedidos_novos():
    with _banco() as conexao:
        total = conexao.execute(
            "SELECT COUNT(*) FROM pedido WHERE status = 'novo'"
        ).fetchone()[0]
    return jsonify(novos=total)


@orders.route('/admin/qrcode')
def qrcode_cardapio():
    return render_template(
        'admin/qrcode.html',
        catalogo_url=url_for('viewer_categoria', _external=True),
    )