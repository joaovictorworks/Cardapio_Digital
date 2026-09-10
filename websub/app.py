from flask import Flask, render_template
import sqlite3
app = Flask(__name__)

@app.route("/")
@app.route("/index")
def index():
    return render_template("admin/index.html")

def conexao():
    conn = sqlite3.connect('database.db')
    return conn

@app.route("/listar_categorias")
def lsitarCategorias():
    conn = conexao()
    categoria = conn.execute('select * from categoria')
    return render_template('admin/lista_categoria.html',
                           categoria = categoria)

@app.route("/listar_produtos")
def lsitarProdutos():
    return render_template('admin/listar_produtos.html')

app.run(debug=True )