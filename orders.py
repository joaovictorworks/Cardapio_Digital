from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from database import abrir_banco


orders = Blueprint('orders', __name__)
STATUS_PEDIDO = {
    'novo': 'Novo',
    'aceito': 'Aceito',
    'preparando': 'Em preparo',
    'pronto': 'Pronto',
    'concluido': 'Concluído',
    'cancelado': 'Cancelado',
}


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
                   (cliente_nome, cliente_telefone, observacoes, status, total_centavos)
                   VALUES (?, ?, ?, 'novo', ?)''',
                (nome, telefone or None, observacoes or None, total_centavos),
            )
            pedido_id = cursor.lastrowid
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

    flash(f'Pedido #{pedido_id} enviado! O estabelecimento já pode recebê-lo.', 'success')
    return redirect(url_for('viewer_categoria'))


@orders.route('/admin/pedidos')
def listar_pedidos():
    with _banco() as conexao:
        pedidos = conexao.execute(
            '''SELECT id, cliente_nome, cliente_telefone, observacoes,
                      status, total_centavos, criado_em
               FROM pedido
               ORDER BY CASE status WHEN 'novo' THEN 0 ELSE 1 END, id DESC'''
        ).fetchall()
        itens = conexao.execute(
            '''SELECT pedido_id, produto_nome, quantidade,
                      preco_unitario_centavos, subtotal_centavos
               FROM item_pedido
               ORDER BY id'''
        ).fetchall()

    itens_por_pedido = {}
    for item in itens:
        itens_por_pedido.setdefault(item['pedido_id'], []).append(item)

    return render_template(
        'admin/pedidos.html',
        pedidos=pedidos,
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
