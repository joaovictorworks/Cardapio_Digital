# Cardápio e pedidos

Aplicação Flask com catálogo público para clientes e painel administrativo para
gerenciar produtos e acompanhar pedidos.

## Estrutura principal

- `app.py`: configuração Flask, autenticação e rotas existentes de cadastro.
- `orders.py`: criação de pedidos, painel/estados dos pedidos, contador de novos
  pedidos e página de QR Code.
- `database.py` e `banco.sql`: conexão SQLite e criação/migração aditiva do
  esquema.
- `templates/site/`: cardápio público e envio do pedido.
- `templates/admin/`: administração, fila de pedidos e QR Code.
- `tests/`: testes do fluxo de pedidos.

## Executar

1. Crie e ative um ambiente virtual.
2. Instale as dependências com `pip install -r requirements.txt`.
3. Execute `python init_db.py` para criar ou atualizar o banco.
   A atualização é não destrutiva: não apaga usuários, categorias ou produtos.
4. Defina `FLASK_SECRET_KEY` com um segredo estável antes de iniciar o servidor.
5. Inicie com `python app.py` e abra `http://127.0.0.1:5005`.

No primeiro acesso, use o link de cadastro na tela de login para criar a conta
administrativa inicial. Depois disso, somente uma sessão autenticada pode
cadastrar outras contas.

O QR Code usa o endereço público configurado para a aplicação. Em produção, use
um domínio acessível pelos clientes e HTTPS; endereços locais como `localhost`
funcionam apenas na própria máquina.

## Fluxo atual

1. O cliente abre o catálogo público, escolhe quantidades e informa o nome.
2. O servidor valida disponibilidade e preço dos produtos e grava o pedido e
   seus itens numa transação SQLite, preservando nome/preço como fotografia do
   momento da compra.
3. O cliente recebe um código secreto de acompanhamento após enviar o pedido.
   Na página pública, o status é atualizado automaticamente a cada 10 segundos
   enquanto ela estiver aberta.
4. O painel administrativo lista os pedidos e permite atualizar o estado. Um
   contador consulta novos pedidos a cada 15 segundos enquanto o painel está
   aberto.
5. O administrador pode abrir/imprimir o QR Code para compartilhar o catálogo.

O pedido registra uma solicitação para o estabelecimento; pagamento e
confirmação de entrega não fazem parte desta etapa.

## Testes

Execute `python -m unittest discover -s tests`.
