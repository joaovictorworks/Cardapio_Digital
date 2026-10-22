CREATE TABLE IF NOT EXISTS categoria(
   id integer primary key autoincrement,
   nome varchar(50) not null,
   descricao text, 
   ativo boolean,
   imagem blob,
   img varchar(100)
);

CREATE TABLE IF NOT EXISTS produto(
   id integer primary key autoincrement,
   nome varchar(50) not null,
   preco float,
   ativo boolean, 
   imagem blob,
   img varchar(100),
   id_categoria int,
   foreign key (id_categoria) references categoria(id)
);

CREATE TABLE IF NOT EXISTS usuario (
    id integer primary key AUTOINCREMENT,
    nome varchar(50) not null,
    senha varchar (50) not null,
    ativo boolean

);

CREATE TABLE IF NOT EXISTS pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_nome TEXT NOT NULL CHECK(length(cliente_nome) BETWEEN 1 AND 100),
    cliente_telefone TEXT,
    observacoes TEXT,
    status TEXT NOT NULL DEFAULT 'novo'
        CHECK(status IN ('novo', 'aceito', 'preparando', 'pronto', 'concluido', 'cancelado')),
    total_centavos INTEGER NOT NULL CHECK(total_centavos >= 0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_pedido (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    produto_id INTEGER,
    produto_nome TEXT NOT NULL,
    quantidade INTEGER NOT NULL CHECK(quantidade BETWEEN 1 AND 99),
    preco_unitario_centavos INTEGER NOT NULL CHECK(preco_unitario_centavos >= 0),
    subtotal_centavos INTEGER NOT NULL CHECK(subtotal_centavos >= 0)
);

CREATE INDEX IF NOT EXISTS idx_pedido_status_criado
    ON pedido(status, criado_em);
CREATE INDEX IF NOT EXISTS idx_item_pedido_pedido_id
    ON item_pedido(pedido_id);
