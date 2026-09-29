import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "FLASK_SECRET_KEY",
    "chave-local-apenas-para-desenvolvimento"
)

database_url = os.getenv("DATABASE_URL", "").strip()

# Compatibilidade com URLs antigas do Render
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Permite testar localmente antes de configurar o PostgreSQL
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///empreiteiras.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ============================================================
# MODELOS
# ============================================================

class Empresa(db.Model):
    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(150), nullable=False)
    nome_fantasia = db.Column(db.String(150), nullable=False)
    cnpj = db.Column(db.String(30), unique=True, nullable=True)
    telefone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    endereco = db.Column(db.String(255), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    usuarios = db.relationship(
        "Usuario",
        backref="empresa",
        lazy=True
    )

    obras = db.relationship(
        "Obra",
        backref="empresa",
        lazy=True
    )


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(150), nullable=False)

    usuario = db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    senha_hash = db.Column(
        db.String(255),
        nullable=False
    )

    funcao = db.Column(
        db.String(50),
        nullable=False,
        default="funcionario"
    )

    ativo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresas.id"),
        nullable=True
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha):
        return check_password_hash(
            self.senha_hash,
            senha
        )


class Obra(db.Model):
    __tablename__ = "obras"

    id = db.Column(db.Integer, primary_key=True)

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresas.id"),
        nullable=False
    )

    nome = db.Column(
        db.String(150),
        nullable=False
    )

    cliente = db.Column(
        db.String(150),
        nullable=True
    )

    endereco = db.Column(
        db.String(255),
        nullable=True
    )

    responsavel = db.Column(
        db.String(150),
        nullable=True
    )

    data_inicio = db.Column(
        db.Date,
        nullable=True
    )

    previsao_termino = db.Column(
        db.Date,
        nullable=True
    )

    status = db.Column(
        db.String(40),
        default="planejamento",
        nullable=False
    )

    observacoes = db.Column(
        db.Text,
        nullable=True
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Material(db.Model):
    __tablename__ = "materiais"

    id = db.Column(db.Integer, primary_key=True)

    categoria = db.Column(
        db.String(100),
        nullable=False
    )

    nome = db.Column(
        db.String(150),
        nullable=False
    )

    descricao = db.Column(
        db.String(255),
        nullable=True
    )

    unidade = db.Column(
        db.String(30),
        nullable=False
    )

    estoque_minimo = db.Column(
        db.Float,
        default=0
    )

    estoque_atual = db.Column(
        db.Float,
        default=0
    )

    ativo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class Solicitacao(db.Model):
    __tablename__ = "solicitacoes"

    id = db.Column(db.Integer, primary_key=True)

    obra_id = db.Column(
        db.Integer,
        db.ForeignKey("obras.id"),
        nullable=False
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("materiais.id"),
        nullable=False
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=False
    )

    quantidade = db.Column(
        db.Float,
        nullable=False
    )

    observacao = db.Column(
        db.Text,
        nullable=True
    )

    status = db.Column(
        db.String(40),
        default="pendente",
        nullable=False
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    obra = db.relationship("Obra")
    material = db.relationship("Material")
    usuario = db.relationship("Usuario")


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def usuario_atual():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    return db.session.get(Usuario, usuario_id)


def login_obrigatorio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        if not session.get("usuario_id"):
            flash(
                "Faça login para continuar.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        usuario = usuario_atual()

        if not usuario or not usuario.ativo:
            session.clear()

            flash(
                "Usuário inválido ou desativado.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        return func(*args, **kwargs)

    return wrapper


@app.context_processor
def dados_globais():
    return {
        "usuario_logado": usuario_atual()
    }


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    with app.app_context():

        db.create_all()

        # Cria empresa padrão somente se não existir
        empresa = Empresa.query.first()

        if not empresa:

            empresa = Empresa(
                razao_social="Empresa de Construção",
                nome_fantasia="Construtora",
                ativo=True
            )

            db.session.add(empresa)
            db.session.commit()

        # Cria administrador inicial somente se não existir
        admin_usuario = os.getenv(
            "ADMIN_USER",
            "admin"
        )

        admin_senha = os.getenv(
            "ADMIN_PASSWORD",
            ""
        )

        usuario = Usuario.query.filter_by(
            usuario=admin_usuario
        ).first()

        if not usuario and admin_senha:

            usuario = Usuario(
                nome="Administrador",
                usuario=admin_usuario,
                funcao="administrador",
                empresa_id=empresa.id,
                ativo=True
            )

            usuario.definir_senha(admin_senha)

            db.session.add(usuario)
            db.session.commit()


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("usuario_id"):
        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        usuario_digitado = request.form.get(
            "usuario",
            ""
        ).strip()

        senha = request.form.get(
            "senha",
            ""
        )

        usuario = Usuario.query.filter_by(
            usuario=usuario_digitado
        ).first()

        if (
            usuario
            and usuario.ativo
            and usuario.verificar_senha(senha)
        ):

            session.clear()

            session["usuario_id"] = usuario.id

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Usuário ou senha inválidos.",
            "danger"
        )

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    flash(
        "Sessão encerrada.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_obrigatorio
def dashboard():

    usuario = usuario_atual()

    obras_query = Obra.query

    if usuario.empresa_id:
        obras_query = obras_query.filter_by(
            empresa_id=usuario.empresa_id
        )

    obras = obras_query.all()

    total_obras = len(obras)

    obras_ativas = sum(
        1
        for obra in obras
        if obra.status == "andamento"
    )

    total_materiais = Material.query.filter_by(
        ativo=True
    ).count()

    materiais_baixos = Material.query.filter(
        Material.ativo.is_(True),
        Material.estoque_atual <= Material.estoque_minimo
    ).count()

    solicitacoes_pendentes = Solicitacao.query.filter_by(
        status="pendente"
    ).count()

    return render_template(
        "dashboard.html",
        total_obras=total_obras,
        obras_ativas=obras_ativas,
        total_materiais=total_materiais,
        materiais_baixos=materiais_baixos,
        solicitacoes_pendentes=solicitacoes_pendentes
    )


# ============================================================
# OBRAS
# ============================================================

@app.route("/obras")
@login_obrigatorio
def obras():

    usuario = usuario_atual()

    query = Obra.query

    if usuario.empresa_id:
        query = query.filter_by(
            empresa_id=usuario.empresa_id
        )

    lista = query.order_by(
        Obra.id.desc()
    ).all()

    return render_template(
        "obras.html",
        obras=lista
    )


@app.route("/obras/nova", methods=["GET", "POST"])
@login_obrigatorio
def nova_obra():

    usuario = usuario_atual()

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        if not nome:

            flash(
                "Informe o nome da obra.",
                "danger"
            )

            return redirect(
                url_for("nova_obra")
            )

        obra = Obra(
            empresa_id=usuario.empresa_id,
            nome=nome,
            cliente=request.form.get(
                "cliente",
                ""
            ).strip(),
            endereco=request.form.get(
                "endereco",
                ""
            ).strip(),
            responsavel=request.form.get(
                "responsavel",
                ""
            ).strip(),
            status=request.form.get(
                "status",
                "planejamento"
            ),
            observacoes=request.form.get(
                "observacoes",
                ""
            ).strip()
        )

        db.session.add(obra)
        db.session.commit()

        flash(
            "Obra cadastrada com sucesso.",
            "success"
        )

        return redirect(
            url_for("obras")
        )

    return render_template(
        "obra_form.html",
        obra=None
    )


# ============================================================
# MATERIAIS
# ============================================================

@app.route("/materiais")
@login_obrigatorio
def materiais():

    lista = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.categoria,
        Material.nome
    ).all()

    return render_template(
        "materiais.html",
        materiais=lista
    )


@app.route("/materiais/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_material():

    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()

        categoria = request.form.get(
            "categoria",
            ""
        ).strip()

        unidade = request.form.get(
            "unidade",
            ""
        ).strip()

        if not nome or not categoria or not unidade:

            flash(
                "Preencha nome, categoria e unidade.",
                "danger"
            )

            return redirect(
                url_for("novo_material")
            )

        try:

            estoque_minimo = float(
                request.form.get(
                    "estoque_minimo",
                    0
                ) or 0
            )

            estoque_atual = float(
                request.form.get(
                    "estoque_atual",
                    0
                ) or 0
            )

        except ValueError:

            flash(
                "Quantidade de estoque inválida.",
                "danger"
            )

            return redirect(
                url_for("novo_material")
            )

        material = Material(
            categoria=categoria,
            nome=nome,
            descricao=request.form.get(
                "descricao",
                ""
            ).strip(),
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual
        )

        db.session.add(material)
        db.session.commit()

        flash(
            "Material cadastrado com sucesso.",
            "success"
        )

        return redirect(
            url_for("materiais")
        )

    return render_template(
        "material_form.html"
    )


# ============================================================
# SOLICITAÇÕES
# ============================================================

@app.route("/solicitacoes")
@login_obrigatorio
def solicitacoes():

    usuario = usuario_atual()

    query = Solicitacao.query

    if usuario.empresa_id:

        query = query.join(
            Obra,
            Solicitacao.obra_id == Obra.id
        ).filter(
            Obra.empresa_id == usuario.empresa_id
        )

    lista = query.order_by(
        Solicitacao.id.desc()
    ).all()

    return render_template(
        "solicitacoes.html",
        solicitacoes=lista
    )


@app.route(
    "/solicitacoes/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def nova_solicitacao():

    usuario = usuario_atual()

    obras = Obra.query.filter_by(
        empresa_id=usuario.empresa_id
    ).order_by(
        Obra.nome
    ).all()

    materiais = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.nome
    ).all()

    if request.method == "POST":

        try:

            obra_id = int(
                request.form.get("obra_id")
            )

            material_id = int(
                request.form.get("material_id")
            )

            quantidade = float(
                request.form.get("quantidade")
            )

        except (ValueError, TypeError):

            flash(
                "Dados da solicitação inválidos.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        obra = db.session.get(
            Obra,
            obra_id
        )

        material = db.session.get(
            Material,
            material_id
        )

        if not obra or obra.empresa_id != usuario.empresa_id:

            flash(
                "Obra inválida.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if not material or not material.ativo:

            flash(
                "Material inválido.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if quantidade <= 0:

            flash(
                "A quantidade deve ser maior que zero.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        solicitacao = Solicitacao(
            obra_id=obra.id,
            material_id=material.id,
            usuario_id=usuario.id,
            quantidade=quantidade,
            observacao=request.form.get(
                "observacao",
                ""
            ).strip(),
            status="pendente"
        )

        db.session.add(solicitacao)
        db.session.commit()

        flash(
            "Solicitação enviada com sucesso.",
            "success"
        )

        return redirect(
            url_for("solicitacoes")
        )

    return render_template(
        "solicitacao_form.html",
        obras=obras,
        materiais=materiais
    )


# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    return render_template(
        "404.html"
    ), 404


@app.errorhandler(500)
def erro_interno(error):

    db.session.rollback()

    return render_template(
        "500.html"
    ), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

with app.app_context():
    inicializar_banco()


if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
