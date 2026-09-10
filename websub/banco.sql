DROP TABLE
IF
  EXISTS produtos;
  DROP TABLE
  IF
    EXISTS categoria;
    DROP TABLE
    IF
      EXISTS usuario;

      CREATE TABLE categoria(
        id integer primary key autoincrement
        , nome varchar(50) not null
        , descricao text
        , ativo boolean
        , imagem blob
        , img varchar(100)
      );

      CREATE TABLE produtos(
        id integer primary key autoincrement
        , nome varchar(50) not null
        , preco float
        , ativo boolean
        , imagem blob
        , img varchar(100)
        , id_categoria int
        , foreign key (id_categoria) references categoria(id)
      );

      CREATE TABLE usuario(
        id integer primary key autoincrement
        , nome varchar(50) not null
        , senha varchar(50) not null
        , ativo boolean
      );

      insert into
        categoria(nome, descricao, ativo)
      values
        ('vodka', 'Orloff', 'True')
        , ('Coca Cola', 'Lata', 'True')