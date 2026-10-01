import os
import logging
import threading
import unicodedata
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    UserMixin,
    LoginManager,
    login_user,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "FLASK_SECRET_KEY",
    "chave-temporaria-construtora-pro"
)

database_url = os.getenv("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url

else:
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///construtora_pro.db"
    )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"

logging.basicConfig(level=logging.INFO)


# ============================================================
# CONSTANTES
# ============================================================

FUNCOES_FUNCIONARIOS = {
    "mestre_obra": "Mestre de Obra",
    "pedreiro": "Pedreiro",
    "ajudante": "Ajudante",
    "compras": "Compras",
    "almoxarife": "Almoxarife",
    "funcionario": "Funcionário",
}

STATUS_OBRA = {
    "planejamento": "Planejamento",
    "em_andamento": "Em andamento",
    "pausada": "Pausada",
    "concluida": "Concluída",
}

STATUS_SOLICITACAO = {
    "pendente": "Pendente",
    "comprado": "Comprado",
    "confirmado": "Confirmado",
    "cancelado": "Cancelado",
}

TIPOS_SOLICITACAO = {
    "material": "Material",
    "ferramenta": "Ferramenta",
    "outro": "Outro",
}

FUNCOES_OPERACIONAIS = {
    "mestre_obra",
    "pedreiro",
    "ajudante",
    "compras",
    "almoxarife",
    "funcionario",
}

FUNCOES_ESTOQUE = {
    "mestre_obra",
    "pedreiro",
    "ajudante",
    "compras",
    "almoxarife",
}

FUNCOES_COMPRAS = {
    "compras",
    "almoxarife",
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_cnpj(valor):
    return "".join(
        ch for ch in (valor or "")
        if ch.isdigit()
    )


def normalizar_usuario(valor):
    return (valor or "").strip().lower()


def normalizar_texto(valor):
    valor = str(valor or "").strip().lower()
    valor = unicodedata.normalize("NFKD", valor)

    return "".join(
        c for c in valor
        if not unicodedata.combining(c)
    )


def funcao_atual():

    if not current_user.is_authenticated:
        return None

    return (
        current_user.funcao or ""
    ).strip().lower()


def empresa_atual_obrigatoria():

    if (
        not current_user.is_authenticated
        or eh_administrador()
    ):
        return None

    return empresa_usuario_atual()


def usuario_eh_funcao(*funcoes):

    return funcao_atual() in set(funcoes)


def usuario_atual():

    if not current_user.is_authenticated:
        return None

    return current_user


def eh_administrador():

    if not current_user.is_authenticated:
        return False

    return (
        (current_user.funcao or "").strip().lower()
        == "adm"
    )


def eh_administrador_empresa():

    if not current_user.is_authenticated:
        return False

    return (
        (current_user.funcao or "").strip().lower()
        in (
            "administrador_empresa",
            "admin_empresa",
        )
    )


def eh_gestor_empresa():

    return (
        eh_administrador()
        or eh_administrador_empresa()
    )


def eh_compras():

    return (
        eh_administrador_empresa()
        or funcao_atual() in FUNCOES_COMPRAS
    )


def empresa_usuario_atual():

    if not current_user.is_authenticated:
        return None

    if not current_user.empresa_id:
        return None

    return db.session.get(
        Empresa,
        current_user.empresa_id
    )


def obter_obra(obra_id):

    return db.session.get(
        Obra,
        obra_id
    )


def obter_material(material_id):

    return db.session.get(
        Material,
        material_id
    )


def obter_ferramenta(ferramenta_id):

    return db.session.get(
        Ferramenta,
        ferramenta_id
    )


def usuario_tem_acesso_obra(usuario, obra):

    if not usuario or not obra:
        return False

    if usuario.funcao == "adm":
        return False

    if usuario.funcao in (
        "administrador_empresa",
        "admin_empresa",
    ):

        return (
            usuario.empresa_id
            == obra.empresa_id
        )

    vinculo = UsuarioObra.query.filter_by(
        usuario_id=usuario.id,
        obra_id=obra.id,
    ).first()

    return vinculo is not None


def obras_do_usuario(usuario=None):

    usuario = usuario or current_user

    if not usuario or not usuario.is_authenticated:
        return []

    if usuario.funcao == "adm":

        return []

    if usuario.funcao in (
        "administrador_empresa",
        "admin_empresa",
    ):

        return Obra.query.filter_by(
            empresa_id=usuario.empresa_id
        ).order_by(
            Obra.criado_em.desc()
        ).all()

    vinculos = UsuarioObra.query.filter_by(
        usuario_id=usuario.id
    ).all()

    obra_ids = [
        vinculo.obra_id
        for vinculo in vinculos
    ]

    if not obra_ids:
        return []

    return Obra.query.filter(
        Obra.id.in_(obra_ids)
    ).order_by(
        Obra.criado_em.desc()
    ).all()


def usuario_pode_gerenciar_obra(obra):

    if not current_user.is_authenticated:
        return False

    if eh_administrador():
        return False

    if eh_administrador_empresa():

        return (
            current_user.empresa_id
            == obra.empresa_id
        )

    return False


# ============================================================
# CONTROLE DE ACESSO DA EMPREITEIRA
# ============================================================

def empresa_admin_obrigatorio(func):

    @wraps(func)
    def decorated_function(*args, **kwargs):

        if not current_user.is_authenticated:

            flash(
                "Faça login para acessar esta página.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if not current_user.ativo:

            logout_user()

            flash(
                "Seu usuário está inativo.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # O ADM GERAL NÃO possui acesso operacional.
        # Somente o ADM da própria empreiteira pode executar
        # estas funções.

        if not eh_administrador_empresa():

            flash(
                "Esta função pertence ao ADM da empreiteira.",
                "danger"
            )

            if eh_administrador():

                return redirect(
                    url_for("admin_dashboard")
                )

            return redirect(
                url_for("dashboard")
            )

        empresa = empresa_usuario_atual()

        if not empresa or not empresa.ativo:

            logout_user()

            flash(
                "A empreiteira está bloqueada ou não existe.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        return func(*args, **kwargs)

    return decorated_function


def empresa_acesso_obrigatorio(func):

    @wraps(func)
    def decorated_function(*args, **kwargs):

        if not current_user.is_authenticated:

            flash(
                "Faça login para acessar esta página.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if not current_user.ativo:

            logout_user()

            flash(
                "Seu usuário está inativo.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # BLOQUEIO DEFINITIVO DO ADM GERAL
        # em módulos operacionais.

        if eh_administrador():

            flash(
                "O ADM geral possui somente acesso administrativo "
                "ao cadastro das empreiteiras.",
                "warning"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        empresa = empresa_usuario_atual()

        if not empresa or not empresa.ativo:

            logout_user()

            flash(
                "A empreiteira está bloqueada ou não existe.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        return func(*args, **kwargs)

    return decorated_function


def estoque_obrigatorio(func):

    @wraps(func)
    @empresa_acesso_obrigatorio
    def decorated_function(*args, **kwargs):

        if (
            funcao_atual() not in FUNCOES_ESTOQUE
            and not eh_administrador_empresa()
        ):

            flash(
                "Seu perfil não possui acesso a estoque, "
                "materiais e ferramentas.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return func(*args, **kwargs)

    return decorated_function


def compras_obrigatorio(func):

    @wraps(func)
    @empresa_acesso_obrigatorio
    def decorated_function(*args, **kwargs):

        if (
            not eh_administrador_empresa()
            and funcao_atual() not in FUNCOES_COMPRAS
        ):

            flash(
                "Somente o ADM da empreiteira, Compras "
                "ou Almoxarifado podem executar esta operação.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return func(*args, **kwargs)

    return decorated_function


def mestre_ou_admin_obrigatorio(func):

    @wraps(func)
    @empresa_acesso_obrigatorio
    def decorated_function(*args, **kwargs):

        if (
            not eh_administrador_empresa()
            and funcao_atual() != "mestre_obra"
        ):

            flash(
                "Somente o ADM da empreiteira ou o "
                "Mestre de Obra pode acessar esta função.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return func(*args, **kwargs)

    return decorated_function


# ============================================================
# LOGIN OBRIGATÓRIO
# ============================================================

def login_obrigatorio(func):

    @wraps(func)
    def decorated_function(*args, **kwargs):

        if not current_user.is_authenticated:

            flash(
                "Faça login para acessar esta página.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if not current_user.ativo:

            logout_user()

            flash(
                "Seu usuário está inativo.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # ADM Geral não possui empresa vinculada.

        if eh_administrador():

            return func(
                *args,
                **kwargs
            )

        empresa = empresa_usuario_atual()

        if not empresa or not empresa.ativo:

            logout_user()

            flash(
                "A empresa vinculada a este usuário "
                "está inativa ou não existe.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        return func(
            *args,
            **kwargs
        )

    return decorated_function


# ============================================================
# ADM GERAL
# ============================================================

def admin_obrigatorio(func):

    @wraps(func)
    @login_obrigatorio
    def decorated_function(*args, **kwargs):

        if not eh_administrador():

            flash(
                "Acesso permitido somente ao ADM geral.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return func(
            *args,
            **kwargs
        )

    return decorated_function


# ============================================================
# MODELOS
# ============================================================

class Empresa(db.Model):

    __tablename__ = "empresas"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    razao_social = db.Column(
        db.String(200),
        nullable=False
    )

    nome_fantasia = db.Column(
        db.String(200),
        nullable=False
    )

    cnpj = db.Column(
        db.String(30),
        unique=True,
        nullable=True
    )

    telefone = db.Column(
        db.String(50)
    )

    email = db.Column(
        db.String(150)
    )

    endereco = db.Column(
        db.String(300)
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

    materiais = db.relationship(
        "Material",
        backref="empresa",
        lazy=True
    )

    ferramentas = db.relationship(
        "Ferramenta",
        backref="empresa",
        lazy=True
    )


class Usuario(UserMixin, db.Model):

    __tablename__ = "usuarios"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nome = db.Column(
        db.String(150),
        nullable=False
    )

    usuario = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    senha_hash = db.Column(
        db.String(255),
        nullable=False
    )

    funcao = db.Column(
        db.String(80),
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

    solicitacoes = db.relationship(
        "Solicitacao",
        foreign_keys="Solicitacao.usuario_id",
        backref="solicitante",
        lazy=True
    )

    solicitacoes_confirmadas = db.relationship(
        "Solicitacao",
        foreign_keys="Solicitacao.confirmado_por_id",
        backref="confirmado_por",
        lazy=True
    )

    def definir_senha(self, senha):

        self.senha_hash = generate_password_hash(
            senha
        )

    def verificar_senha(self, senha):

        return check_password_hash(
            self.senha_hash,
            senha
        )


class Obra(db.Model):

    __tablename__ = "obras"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresas.id"),
        nullable=False
    )

    nome = db.Column(
        db.String(200),
        nullable=False
    )

    cliente = db.Column(
        db.String(200)
    )

    endereco = db.Column(
        db.String(300)
    )

    responsavel = db.Column(
        db.String(150)
    )

    data_inicio = db.Column(
        db.Date
    )

    previsao_termino = db.Column(
        db.Date
    )

    status = db.Column(
        db.String(50),
        default="planejamento",
        nullable=False
    )

    observacoes = db.Column(
        db.Text
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    solicitacoes = db.relationship(
        "Solicitacao",
        backref="obra",
        lazy=True,
        cascade="all, delete-orphan"
    )

    vinculos_usuarios = db.relationship(
        "UsuarioObra",
        backref="obra",
        lazy=True,
        cascade="all, delete-orphan"
    )

    @property
    def equipe(self):

        return self.vinculos_usuarios


class UsuarioObra(db.Model):

    __tablename__ = "usuario_obras"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=False
    )

    obra_id = db.Column(
        db.Integer,
        db.ForeignKey("obras.id"),
        nullable=False
    )

    funcao_na_obra = db.Column(
        db.String(80),
        nullable=False,
        default="funcionario"
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    usuario = db.relationship(
        "Usuario",
        backref=db.backref(
            "vinculos_obras",
            lazy=True
        )
    )

    __table_args__ = (
        db.UniqueConstraint(
            "usuario_id",
            "obra_id",
            name="uq_usuario_obra"
        ),
    )


class Material(db.Model):

    __tablename__ = "materiais"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresas.id"),
        nullable=True
    )

    categoria = db.Column(
        db.String(120),
        nullable=False
    )

    nome = db.Column(
        db.String(200),
        nullable=False
    )

    descricao = db.Column(
        db.Text
    )

    unidade = db.Column(
        db.String(30),
        default="un"
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

    solicitacoes = db.relationship(
        "Solicitacao",
        backref="material",
        lazy=True
    )


class Ferramenta(db.Model):

    __tablename__ = "ferramentas"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresas.id"),
        nullable=True
    )

    categoria = db.Column(
        db.String(120),
        nullable=False
    )

    nome = db.Column(
        db.String(200),
        nullable=False
    )

    descricao = db.Column(
        db.Text
    )

    unidade = db.Column(
        db.String(30),
        default="un"
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

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    obra_id = db.Column(
        db.Integer,
        db.ForeignKey("obras.id"),
        nullable=False
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("materiais.id"),
        nullable=True
    )

    ferramenta_id = db.Column(
        db.Integer,
        db.ForeignKey("ferramentas.id"),
        nullable=True
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
        db.Text
    )

    status = db.Column(
        db.String(50),
        default="pendente",
        nullable=False
    )

    tipo_recurso = db.Column(
        db.String(30),
        nullable=False,
        default="material"
    )

    recurso_nome = db.Column(
        db.String(200),
        nullable=True
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    confirmado_por_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id"),
        nullable=True
    )

    confirmado_em = db.Column(
        db.DateTime,
        nullable=True
    )

    ferramenta = db.relationship(
        "Ferramenta",
        backref=db.backref(
            "solicitacoes",
            lazy=True
        ),
        lazy=True
    )


# ============================================================
# INICIALIZAÇÃO E COMPATIBILIDADE DO BANCO
# ============================================================

_db_init_lock = threading.Lock()
_db_initialized = False


def _coluna_existe(inspector, tabela, coluna):

    try:
        return any(
            item["name"] == coluna
            for item in inspector.get_columns(tabela)
        )
    except Exception:
        return False


def inicializar_banco():
    """Cria as tabelas e adiciona colunas novas sem apagar dados existentes."""

    db.create_all()

    inspector = inspect(db.engine)

    alteracoes = {
        "materiais": {
            "empresa_id": "INTEGER",
        },
        "ferramentas": {
            "empresa_id": "INTEGER",
        },
        "solicitacoes": {
            "material_id": "INTEGER",
            "ferramenta_id": "INTEGER",
            "tipo_recurso": "VARCHAR(30) DEFAULT 'material'",
            "recurso_nome": "VARCHAR(200)",
            "confirmado_por_id": "INTEGER",
            "confirmado_em": "TIMESTAMP",
        },
    }

    for tabela, colunas in alteracoes.items():

        if tabela not in inspector.get_table_names():
            continue

        for coluna, definicao in colunas.items():

            if _coluna_existe(inspector, tabela, coluna):
                continue

            sql = (
                f"ALTER TABLE {tabela} "
                f"ADD COLUMN {coluna} {definicao}"
            )

            try:
                with db.engine.begin() as conn:
                    conn.execute(text(sql))

            except Exception:
                logging.exception(
                    "Falha ao adicionar coluna %s.%s",
                    tabela,
                    coluna,
                )
                raise

            inspector = inspect(db.engine)

    # Garante valor válido para registros antigos.
    if "solicitacoes" in inspector.get_table_names():
        try:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE solicitacoes "
                        "SET tipo_recurso = 'material' "
                        "WHERE tipo_recurso IS NULL "
                        "OR tipo_recurso = ''"
                    )
                )
        except Exception:
            logging.exception(
                "Falha ao normalizar tipo_recurso das solicitações"
            )
            raise


@app.before_request
def garantir_banco_inicializado():

    global _db_initialized

    if _db_initialized:
        return None

    with _db_init_lock:

        if _db_initialized:
            return None

        try:
            inicializar_banco()
            _db_initialized = True

            logging.info(
                "Banco de dados inicializado com sucesso."
            )

        except Exception:

            logging.exception(
                "Não foi possível inicializar o banco de dados."
            )

            return (
                "Banco de dados indisponível. "
                "Verifique os logs do serviço.",
                503,
            )

    return None


# ============================================================
# LOGIN MANAGER
# ============================================================

@login_manager.user_loader
def load_user(user_id):

    try:

        return db.session.get(
            Usuario,
            int(user_id)
        )

    except (
        ValueError,
        TypeError
    ):

        return None


# ============================================================
# CONTEXT PROCESSOR
# ============================================================

@app.context_processor
def injetar_contexto():

    empresa = None

    if current_user.is_authenticated:

        empresa = empresa_usuario_atual()

    return {
        "usuario_logado": current_user,
        "eh_adm": eh_administrador(),
        "eh_adm_empresa": eh_administrador_empresa(),
        "eh_gestor": eh_gestor_empresa(),
        "empresa_atual": empresa,
        "funcoes_funcionarios": FUNCOES_FUNCIONARIOS,
        "status_obras": STATUS_OBRA,
        "status_solicitacoes": STATUS_SOLICITACAO,
        "now": datetime.now,
    }


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user.is_authenticated:

        if eh_administrador():

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("empresa_dashboard")
        )

    if request.method == "POST":

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = request.form.get(
            "senha",
            ""
        )

        usuario = Usuario.query.filter_by(
            usuario=usuario_login
        ).first()

        if not usuario:

            flash(
                "Usuário ou senha inválidos.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if not usuario.ativo:

            flash(
                "Este usuário está inativo.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if not usuario.verificar_senha(senha):

            flash(
                "Usuário ou senha inválidos.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if usuario.funcao == "adm":

            login_user(usuario)

            flash(
                f"Bem-vindo, {usuario.nome}!",
                "success"
            )

            return redirect(
                url_for("admin_dashboard")
            )

        empresa = db.session.get(
            Empresa,
            usuario.empresa_id
        )

        if not empresa or not empresa.ativo:

            flash(
                "A empresa vinculada a este usuário "
                "está inativa ou não existe.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        login_user(usuario)

        flash(
            f"Bem-vindo, {usuario.nome}!",
            "success"
        )

        if usuario.funcao == "equipe_obra":

            vinculo = UsuarioObra.query.filter_by(
                usuario_id=usuario.id
            ).first()

            if vinculo:

                return redirect(
                    url_for(
                        "obra_detalhes",
                        obra_id=vinculo.obra_id
                    )
                )

        return redirect(
            url_for("empresa_dashboard")
        )


    return render_template(
        "login.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_obrigatorio
def dashboard():

    if eh_administrador():

        return redirect(
            url_for("admin_dashboard")
        )

    return redirect(
        url_for("empresa_dashboard")
    )


# ============================================================
# PAINEL DA EMPREITEIRA
# ============================================================

@app.route("/empresa/painel")
@empresa_acesso_obrigatorio
def empresa_dashboard():

    empresa = empresa_usuario_atual()

    obras_count = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    usuarios_count = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    materiais_count = Material.query.filter_by(
        empresa_id=empresa.id,
        ativo=True
    ).count()

    ferramentas_count = Ferramenta.query.filter_by(
        empresa_id=empresa.id,
        ativo=True
    ).count()

    solicitacoes_pendentes = Solicitacao.query.join(
        Obra,
        Solicitacao.obra_id == Obra.id
    ).filter(
        Obra.empresa_id == empresa.id,
        Solicitacao.status == "pendente"
    ).count()

    solicitacoes_compradas = Solicitacao.query.join(
        Obra,
        Solicitacao.obra_id == Obra.id
    ).filter(
        Obra.empresa_id == empresa.id,
        Solicitacao.status == "comprado"
    ).count()

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.criado_em.desc()
    ).limit(10).all()

    return render_template(
        "empresa_dashboard.html",
        empresa=empresa,
        obras=obras,
        obras_count=obras_count,
        usuarios_count=usuarios_count,
        materiais_count=materiais_count,
        ferramentas_count=ferramentas_count,
        solicitacoes_pendentes=solicitacoes_pendentes,
        solicitacoes_compradas=solicitacoes_compradas,
    )


# ============================================================
# DASHBOARD DO ADM GERAL
# ============================================================

@app.route("/admin")
@admin_obrigatorio
def admin_dashboard():

    empresas = Empresa.query.order_by(
        Empresa.nome_fantasia.asc()
    ).all()

    total_empresas = Empresa.query.count()

    empresas_ativas = Empresa.query.filter_by(
        ativo=True
    ).count()

    return render_template(
        "admin_dashboard.html",
        empresas=empresas,
        total_empresas=total_empresas,
        empresas_ativas=empresas_ativas,
    )


# ============================================================
# EMPRESAS — SOMENTE CADASTRO DA PLATAFORMA
# ============================================================

@app.route(
    "/admin/empresas/nova",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def nova_empresa():

    if request.method == "POST":

        razao_social = (
            request.form.get("razao_social") or ""
        ).strip()

        nome_fantasia = (
            request.form.get("nome_fantasia") or ""
        ).strip()

        cnpj = normalizar_cnpj(
            request.form.get("cnpj")
        )

        telefone = (
            request.form.get("telefone") or ""
        ).strip()

        email = (
            request.form.get("email") or ""
        ).strip()

        endereco = (
            request.form.get("endereco") or ""
        ).strip()

        if not razao_social or not nome_fantasia:

            flash(
                "Razão social e nome fantasia são obrigatórios.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=None,
                titulo="Nova empresa"
            )

        if cnpj and Empresa.query.filter_by(cnpj=cnpj).first():

            flash(
                "Já existe uma empresa com este CNPJ.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=None,
                titulo="Nova empresa"
            )

        empresa = Empresa(
            razao_social=razao_social,
            nome_fantasia=nome_fantasia,
            cnpj=cnpj or None,
            telefone=telefone,
            email=email,
            endereco=endereco,
            ativo=True,
        )

        db.session.add(empresa)

        try:

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível cadastrar a empresa. Verifique os dados.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=None,
                titulo="Nova empresa"
            )

        flash(
            "Empresa cadastrada com sucesso. Agora cadastre o ADM responsável.",
            "success"
        )

        return redirect(
            url_for(
                "novo_administrador_empresa",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "empresa_form.html",
        empresa=None,
        titulo="Nova empresa"
    )


@app.route("/admin/empresas/<int:empresa_id>")
@admin_obrigatorio
def empresa_detalhes(empresa_id):

    return redirect(
        url_for(
            "monitorar_empresa",
            empresa_id=empresa_id
        )
    )


@app.route("/admin/empresas/<int:empresa_id>/monitoramento")
@admin_obrigatorio
def monitorar_empresa(empresa_id):
    """Tela cadastral da empresa. Nunca exibe dados operacionais."""

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empreiteira não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    administradores = Usuario.query.filter(
        Usuario.empresa_id == empresa.id,
        Usuario.funcao.in_([
            "administrador_empresa",
            "admin_empresa",
        ])
    ).order_by(
        Usuario.nome.asc()
    ).all()

    return render_template(
        "empresa_monitoramento.html",
        empresa=empresa,
        administradores=administradores,
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def editar_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empreiteira não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

        razao_social = (
            request.form.get("razao_social") or ""
        ).strip()

        nome_fantasia = (
            request.form.get("nome_fantasia") or ""
        ).strip()

        cnpj = normalizar_cnpj(
            request.form.get("cnpj")
        )

        telefone = (
            request.form.get("telefone") or ""
        ).strip()

        email = (
            request.form.get("email") or ""
        ).strip()

        endereco = (
            request.form.get("endereco") or ""
        ).strip()

        if not razao_social or not nome_fantasia:

            flash(
                "Razão social e nome fantasia são obrigatórios.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=empresa,
                titulo="Editar empresa"
            )

        duplicada = Empresa.query.filter(
            Empresa.cnpj == cnpj,
            Empresa.id != empresa.id,
            Empresa.cnpj.isnot(None),
        ).first() if cnpj else None

        if duplicada:

            flash(
                "Já existe outra empresa com este CNPJ.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=empresa,
                titulo="Editar empresa"
            )

        empresa.razao_social = razao_social
        empresa.nome_fantasia = nome_fantasia
        empresa.cnpj = cnpj or None
        empresa.telefone = telefone
        empresa.email = email
        empresa.endereco = endereco

        try:

            db.session.commit()

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível atualizar a empresa.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                empresa=empresa,
                titulo="Editar empresa"
            )

        flash(
            "Dados da empreiteira atualizados com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "empresa_form.html",
        empresa=empresa,
        titulo="Editar empresa"
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/alternar-status",
    methods=["POST"]
)
@admin_obrigatorio
def alternar_status_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empreiteira não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa.ativo = not empresa.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status da empresa"
        )

        flash(
            "Não foi possível alterar o status da empresa.",
            "danger"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa.id
            )
        )

    flash(
        "Empreiteira ativada com sucesso."
        if empresa.ativo
        else "Empreiteira bloqueada com sucesso.",
        "success"
    )

    return redirect(
        url_for(
            "monitorar_empresa",
            empresa_id=empresa.id
        )
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/excluir",
    methods=["POST"]
)
@admin_obrigatorio
def excluir_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empreiteira não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    try:

        # Remove primeiro os registros dependentes para evitar
        # conflitos de chave estrangeira em PostgreSQL/SQLite.
        obras = Obra.query.filter_by(
            empresa_id=empresa.id
        ).all()

        obra_ids = [obra.id for obra in obras]

        if obra_ids:

            Solicitacao.query.filter(
                Solicitacao.obra_id.in_(obra_ids)
            ).delete(
                synchronize_session=False
            )

            UsuarioObra.query.filter(
                UsuarioObra.obra_id.in_(obra_ids)
            ).delete(
                synchronize_session=False
            )

        UsuarioObra.query.filter(
            UsuarioObra.usuario_id.in_(
                db.session.query(Usuario.id).filter(
                    Usuario.empresa_id == empresa.id
                )
            )
        ).delete(
            synchronize_session=False
        )

        Usuario.query.filter_by(
            empresa_id=empresa.id
        ).delete(
            synchronize_session=False
        )

        Obra.query.filter_by(
            empresa_id=empresa.id
        ).delete(
            synchronize_session=False
        )

        Material.query.filter_by(
            empresa_id=empresa.id
        ).delete(
            synchronize_session=False
        )

        Ferramenta.query.filter_by(
            empresa_id=empresa.id
        ).delete(
            synchronize_session=False
        )

        db.session.delete(empresa)
        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao excluir empreiteira %s",
            empresa_id
        )

        flash(
            "Não foi possível excluir a empreiteira. "
            "Verifique se existem registros dependentes.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    flash(
        "Empreiteira excluída com sucesso.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ADMINISTRADORES DA EMPREITEIRA — SOMENTE ADM GERAL
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/administrador/novo",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def novo_administrador_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empreiteira não encontrada.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

        nome = (
            request.form.get("nome") or ""
        ).strip()

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = (
            request.form.get("senha") or ""
        ).strip()

        if not nome or not usuario_login or not senha:

            flash(
                "Nome, usuário e senha são obrigatórios.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=None,
                titulo="Novo administrador"
            )

        if Usuario.query.filter_by(
            usuario=usuario_login
        ).first():

            flash(
                "Este nome de usuário já está em uso.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=None,
                titulo="Novo administrador"
            )

        administrador = Usuario(
            nome=nome,
            usuario=usuario_login,
            funcao="administrador_empresa",
            ativo=True,
            empresa_id=empresa.id,
        )

        administrador.definir_senha(senha)

        db.session.add(administrador)

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao criar administrador da empreiteira"
            )

            flash(
                "Não foi possível criar o administrador.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=None,
                titulo="Novo administrador"
            )

        flash(
            "Administrador da empreiteira criado com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "administrador_empresa_form.html",
        empresa=empresa,
        administrador=None,
        titulo="Novo administrador"
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/administrador/<int:usuario_id>/editar",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def editar_administrador_empresa(
    empresa_id,
    usuario_id
):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    administrador = db.session.get(
        Usuario,
        usuario_id
    )

    if not empresa or not administrador:

        flash(
            "Empresa ou administrador não encontrado.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if (
        administrador.empresa_id != empresa.id
        or administrador.funcao not in {
            "administrador_empresa",
            "admin_empresa",
        }
    ):

        flash(
            "Este usuário não é administrador desta empreiteira.",
            "danger"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa.id
            )
        )

    if request.method == "POST":

        nome = (
            request.form.get("nome") or ""
        ).strip()

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = (
            request.form.get("senha") or ""
        ).strip()

        if not nome or not usuario_login:

            flash(
                "Nome e usuário são obrigatórios.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=administrador,
                titulo="Editar administrador"
            )

        outro_usuario = Usuario.query.filter(
            Usuario.usuario == usuario_login,
            Usuario.id != administrador.id,
        ).first()

        if outro_usuario:

            flash(
                "Este nome de usuário já está em uso.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=administrador,
                titulo="Editar administrador"
            )

        administrador.nome = nome
        administrador.usuario = usuario_login

        if senha:
            administrador.definir_senha(senha)

        # Checkbox marcado mantém ativo; ausência do checkbox bloqueia.
        administrador.ativo = (
            request.form.get("ativo") == "on"
            or request.form.get("ativo") == "1"
            or request.form.get("ativo") == "true"
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar administrador da empreiteira"
            )

            flash(
                "Não foi possível atualizar o administrador.",
                "danger"
            )

            return render_template(
                "administrador_empresa_form.html",
                empresa=empresa,
                administrador=administrador,
                titulo="Editar administrador"
            )

        flash(
            "Administrador atualizado com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "administrador_empresa_form.html",
        empresa=empresa,
        administrador=administrador,
        titulo="Editar administrador"
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/administrador/<int:usuario_id>/alternar-status",
    methods=["POST"]
)
@admin_obrigatorio
def alternar_status_administrador_empresa(
    empresa_id,
    usuario_id
):

    administrador = Usuario.query.filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == empresa_id,
        Usuario.funcao.in_([
            "administrador_empresa",
            "admin_empresa",
        ])
    ).first()

    if not administrador:

        flash(
            "Administrador não encontrado.",
            "danger"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa_id
            )
        )

    administrador.ativo = not administrador.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status do administrador"
        )

        flash(
            "Não foi possível alterar o status do administrador.",
            "danger"
        )

        return redirect(
            url_for(
                "monitorar_empresa",
                empresa_id=empresa_id
            )
        )

    flash(
        "Administrador ativado com sucesso."
        if administrador.ativo
        else "Administrador bloqueado com sucesso.",
        "success"
    )

    return redirect(
        url_for(
            "monitorar_empresa",
            empresa_id=empresa_id
        )
    )


# ============================================================
# USUÁRIOS / FUNCIONÁRIOS
# ============================================================


@app.route(
    "/admin/empresas/<int:empresa_id>/usuarios/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def novo_usuario_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("empresa_dashboard")
        )

    if empresa.id != current_user.empresa_id:

        flash(
            "Você só pode cadastrar funcionários "
            "da sua própria empreiteira.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.nome.asc()
    ).all()

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = request.form.get(
            "senha",
            ""
        )

        funcao = (
            request.form.get("funcao")
            or "funcionario"
        ).strip()

        if funcao not in FUNCOES_FUNCIONARIOS:
            funcao = "funcionario"

        if funcao in {
            "adm",
            "administrador_empresa",
            "admin_empresa"
        }:

            flash(
                "O ADM da empreiteira é gerenciado pelo "
                "ambiente administrativo da própria empresa.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=obras,
                titulo="Novo funcionário"
            )

        if not nome or not usuario_login or not senha:

            flash(
                "Nome, usuário e senha são obrigatórios.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=obras,
                titulo="Novo funcionário"
            )

        if Usuario.query.filter_by(
            usuario=usuario_login
        ).first():

            flash(
                "Este nome de usuário já está sendo utilizado.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=obras,
                titulo="Novo funcionário"
            )

        funcionario = Usuario(
            nome=nome,
            usuario=usuario_login,
            funcao=funcao,
            ativo=True,
            empresa_id=empresa.id,
        )

        funcionario.definir_senha(
            senha
        )

        db.session.add(
            funcionario
        )

        try:

            db.session.flush()

            obra_ids = request.form.getlist(
                "obras"
            )

            for obra_id in obra_ids:

                try:

                    obra_id_int = int(
                        obra_id
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    continue

                obra = db.session.get(
                    Obra,
                    obra_id_int
                )

                if not obra:
                    continue

                if obra.empresa_id != empresa.id:
                    continue

                db.session.add(
                    UsuarioObra(
                        usuario_id=funcionario.id,
                        obra_id=obra.id,
                        funcao_na_obra=funcao,
                    )
                )

            db.session.commit()

            flash(
                "Funcionário cadastrado com sucesso.",
                "success"
            )

            return redirect(
                url_for("funcionarios")
            )

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao cadastrar funcionário"
            )

            flash(
                "Não foi possível cadastrar o funcionário.",
                "danger"
            )

    return render_template(
        "funcionario_form.html",
        funcionario=None,
        empresa=empresa,
        obras=obras,
        titulo="Novo funcionário"
    )
    # ============================================================
# FUNCIONÁRIOS
# ============================================================

@app.route(
    "/funcionarios",
    methods=["GET"]
)
@empresa_admin_obrigatorio
def funcionarios():

    empresa = empresa_usuario_atual()

    usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Usuario.nome.asc()
    ).all()

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.nome.asc()
    ).all()

    return render_template(
        "funcionarios.html",
        funcionarios=usuarios,
        obras=obras,
        empresa=empresa,
    )


@app.route(
    "/funcionarios/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def novo_funcionario():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("empresa_dashboard")
        )

    return redirect(
        url_for(
            "novo_usuario_empresa",
            empresa_id=empresa.id
        )
    )


@app.route(
    "/funcionarios/<int:usuario_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_funcionario(usuario_id):

    funcionario = db.session.get(
        Usuario,
        usuario_id
    )

    if not funcionario:

        flash(
            "Funcionário não encontrado.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    if funcionario.funcao == "adm":

        flash(
            "O ADM geral não pode ser editado por esta tela.",
            "warning"
        )

        return redirect(
            url_for("funcionarios")
        )

    if (
        funcionario.empresa_id
        != current_user.empresa_id
    ):

        flash(
            "Você não possui acesso a este funcionário.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    empresa = db.session.get(
        Empresa,
        funcionario.empresa_id
    )

    if not empresa:

        flash(
            "Empresa do funcionário não encontrada.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.nome.asc()
    ).all()

    vinculos = UsuarioObra.query.filter_by(
        usuario_id=funcionario.id
    ).all()

    obras_selecionadas = {
        vinculo.obra_id
        for vinculo in vinculos
    }

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = request.form.get(
            "senha",
            ""
        )

        funcao = (
            request.form.get("funcao")
            or funcionario.funcao
        ).strip()

        if funcao not in FUNCOES_FUNCIONARIOS:

            funcao = funcionario.funcao

        outro_usuario = Usuario.query.filter(
            Usuario.usuario == usuario_login,
            Usuario.id != funcionario.id
        ).first()

        if outro_usuario:

            flash(
                "Este nome de usuário já está sendo utilizado.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=funcionario,
                empresa=empresa,
                obras=obras,
                obras_selecionadas=obras_selecionadas,
                titulo="Editar funcionário"
            )

        if not nome or not usuario_login:

            flash(
                "Nome e usuário são obrigatórios.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=funcionario,
                empresa=empresa,
                obras=obras,
                obras_selecionadas=obras_selecionadas,
                titulo="Editar funcionário"
            )

        funcionario.nome = nome
        funcionario.usuario = usuario_login
        funcionario.funcao = funcao

        if senha.strip():

            funcionario.definir_senha(
                senha
            )

        try:

            UsuarioObra.query.filter_by(
                usuario_id=funcionario.id
            ).delete(
                synchronize_session=False
            )

            obra_ids = request.form.getlist(
                "obras"
            )

            for obra_id in obra_ids:

                try:

                    obra_id_int = int(
                        obra_id
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    continue

                obra = db.session.get(
                    Obra,
                    obra_id_int
                )

                if not obra:
                    continue

                if obra.empresa_id != empresa.id:
                    continue

                db.session.add(
                    UsuarioObra(
                        usuario_id=funcionario.id,
                        obra_id=obra.id,
                        funcao_na_obra=funcao,
                    )
                )

            db.session.commit()

            flash(
                "Funcionário atualizado com sucesso.",
                "success"
            )

            return redirect(
                url_for("funcionarios")
            )

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar funcionário"
            )

            flash(
                "Não foi possível atualizar o funcionário.",
                "danger"
            )

    return render_template(
        "funcionario_form.html",
        funcionario=funcionario,
        empresa=empresa,
        obras=obras,
        obras_selecionadas=obras_selecionadas,
        titulo="Editar funcionário"
    )


@app.route(
    "/funcionarios/<int:usuario_id>/alternar-status",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def alternar_status_funcionario(usuario_id):

    funcionario = db.session.get(
        Usuario,
        usuario_id
    )

    if not funcionario:

        flash(
            "Funcionário não encontrado.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    if funcionario.funcao == "adm":

        flash(
            "O ADM geral não pode ser alterado por esta tela.",
            "warning"
        )

        return redirect(
            url_for("funcionarios")
        )

    if (
        funcionario.empresa_id
        != current_user.empresa_id
    ):

        flash(
            "Você não possui acesso a este funcionário.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    funcionario.ativo = not funcionario.ativo

    db.session.commit()

    flash(
        "Status do funcionário atualizado.",
        "success"
    )

    return redirect(
        url_for("funcionarios")
    )


# ============================================================
# OBRAS
# ============================================================

@app.route("/obras")
@empresa_acesso_obrigatorio
def obras():

    lista_obras = obras_do_usuario()

    return render_template(
        "obras.html",
        obras=lista_obras
    )


@app.route(
    "/obras/nova",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def nova_obra():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("empresa_dashboard")
        )

    empresas = [empresa]

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        if not nome:

            flash(
                "O nome da obra é obrigatório.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=None,
                empresas=empresas,
                titulo="Nova obra"
            )

        data_inicio = None
        previsao_termino = None

        data_inicio_raw = request.form.get(
            "data_inicio"
        )

        previsao_raw = request.form.get(
            "previsao_termino"
        )

        if data_inicio_raw:

            try:

                data_inicio = datetime.strptime(
                    data_inicio_raw,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Data de início inválida.",
                    "warning"
                )

        if previsao_raw:

            try:

                previsao_termino = datetime.strptime(
                    previsao_raw,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Previsão de término inválida.",
                    "warning"
                )

        status = (
            request.form.get("status")
            or "planejamento"
        ).strip()

        if status not in STATUS_OBRA:

            status = "planejamento"

        obra = Obra(
            empresa_id=empresa.id,
            nome=nome,
            cliente=(
                request.form.get("cliente")
                or ""
            ).strip(),
            endereco=(
                request.form.get("endereco")
                or ""
            ).strip(),
            responsavel=(
                request.form.get("responsavel")
                or ""
            ).strip(),
            data_inicio=data_inicio,
            previsao_termino=previsao_termino,
            status=status,
            observacoes=(
                request.form.get("observacoes")
                or ""
            ).strip(),
        )

        db.session.add(
            obra
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao cadastrar obra"
            )

            flash(
                "Não foi possível cadastrar a obra.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=None,
                empresas=empresas,
                titulo="Nova obra"
            )

        flash(
            "Obra cadastrada com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    return render_template(
        "obra_form.html",
        obra=None,
        empresas=empresas,
        titulo="Nova obra"
    )


@app.route(
    "/obras/<int:obra_id>"
)
@empresa_acesso_obrigatorio
def obra_detalhes(obra_id):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if not usuario_tem_acesso_obra(
        current_user,
        obra
    ):

        flash(
            "Você não possui acesso a esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    vinculos = UsuarioObra.query.filter_by(
        obra_id=obra.id
    ).all()

    solicitacoes = Solicitacao.query.filter_by(
        obra_id=obra.id
    ).order_by(
        Solicitacao.criado_em.desc()
    ).all()

    equipe_acesso = None

    for vinculo in vinculos:

        if vinculo.usuario.funcao == "equipe_obra":

            equipe_acesso = vinculo.usuario

            break

    return render_template(
        "obra_detalhes.html",
        obra=obra,
        vinculos=vinculos,
        solicitacoes=solicitacoes,
        equipe_acesso=equipe_acesso,
    )


@app.route(
    "/obras/<int:obra_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_obra(obra_id):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if not usuario_pode_gerenciar_obra(
        obra
    ):

        flash(
            "Você não possui permissão para editar esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    empresa = empresa_usuario_atual()

    empresas = [empresa]

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        if not nome:

            flash(
                "O nome da obra é obrigatório.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=obra,
                empresas=empresas,
                titulo="Editar obra"
            )

        obra.nome = nome

        obra.cliente = (
            request.form.get("cliente")
            or ""
        ).strip()

        obra.endereco = (
            request.form.get("endereco")
            or ""
        ).strip()

        obra.responsavel = (
            request.form.get("responsavel")
            or ""
        ).strip()

        status = (
            request.form.get("status")
            or obra.status
        ).strip()

        if status in STATUS_OBRA:

            obra.status = status

        obra.observacoes = (
            request.form.get("observacoes")
            or ""
        ).strip()

        data_inicio_raw = request.form.get(
            "data_inicio"
        )

        previsao_raw = request.form.get(
            "previsao_termino"
        )

        if data_inicio_raw:

            try:

                obra.data_inicio = datetime.strptime(
                    data_inicio_raw,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Data de início inválida.",
                    "warning"
                )

        else:

            obra.data_inicio = None

        if previsao_raw:

            try:

                obra.previsao_termino = datetime.strptime(
                    previsao_raw,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                flash(
                    "Previsão de término inválida.",
                    "warning"
                )

        else:

            obra.previsao_termino = None

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar obra"
            )

            flash(
                "Não foi possível atualizar a obra.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=obra,
                empresas=empresas,
                titulo="Editar obra"
            )

        flash(
            "Obra atualizada com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    return render_template(
        "obra_form.html",
        obra=obra,
        empresas=empresas,
        titulo="Editar obra"
    )

# ============================================================
# FINALIZAÇÃO / EXCLUSÃO DE OBRAS
# ============================================================

@app.route(
    "/obras/<int:obra_id>/finalizar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def finalizar_obra(obra_id):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if obra.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    obra.status = "concluida"

    try:

        db.session.commit()

        flash(
            "Obra finalizada com sucesso.",
            "success"
        )

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao finalizar obra"
        )

        flash(
            "Não foi possível finalizar a obra.",
            "danger"
        )

    return redirect(
        url_for(
            "obra_detalhes",
            obra_id=obra.id
        )
    )


@app.route(
    "/obras/<int:obra_id>/excluir",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def excluir_obra(obra_id):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if obra.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    try:

        UsuarioObra.query.filter_by(
            obra_id=obra.id
        ).delete(
            synchronize_session=False
        )

        Solicitacao.query.filter_by(
            obra_id=obra.id
        ).delete(
            synchronize_session=False
        )

        db.session.delete(
            obra
        )

        db.session.commit()

        flash(
            "Obra excluída com sucesso.",
            "success"
        )

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao excluir obra"
        )

        flash(
            "Não foi possível excluir a obra.",
            "danger"
        )

    return redirect(
        url_for("obras")
    )


# ============================================================
# EQUIPE DA OBRA
# ============================================================

@app.route(
    "/obras/<int:obra_id>/equipe",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def equipe_obra(obra_id):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if obra.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    usuarios = Usuario.query.filter_by(
        empresa_id=current_user.empresa_id,
        ativo=True
    ).order_by(
        Usuario.nome.asc()
    ).all()

    if request.method == "POST":

        usuario_id = request.form.get(
            "usuario_id"
        )

        funcao_na_obra = (
            request.form.get("funcao_na_obra")
            or "funcionario"
        ).strip()

        try:

            usuario_id = int(
                usuario_id
            )

        except (
            ValueError,
            TypeError
        ):

            flash(
                "Funcionário inválido.",
                "danger"
            )

            return redirect(
                url_for(
                    "equipe_obra",
                    obra_id=obra.id
                )
            )

        usuario = db.session.get(
            Usuario,
            usuario_id
        )

        if not usuario:

            flash(
                "Funcionário não encontrado.",
                "danger"
            )

            return redirect(
                url_for(
                    "equipe_obra",
                    obra_id=obra.id
                )
            )

        if usuario.empresa_id != current_user.empresa_id:

            flash(
                "O funcionário pertence a outra empresa.",
                "danger"
            )

            return redirect(
                url_for(
                    "equipe_obra",
                    obra_id=obra.id
                )
            )

        existente = UsuarioObra.query.filter_by(
            usuario_id=usuario.id,
            obra_id=obra.id
        ).first()

        if existente:

            existente.funcao_na_obra = (
                funcao_na_obra
            )

            flash(
                "Função do funcionário atualizada na obra.",
                "success"
            )

        else:

            vinculo = UsuarioObra(
                usuario_id=usuario.id,
                obra_id=obra.id,
                funcao_na_obra=funcao_na_obra,
            )

            db.session.add(
                vinculo
            )

            flash(
                "Funcionário adicionado à obra.",
                "success"
            )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao adicionar funcionário à obra"
            )

            flash(
                "Não foi possível atualizar a equipe.",
                "danger"
            )

        return redirect(
            url_for(
                "equipe_obra",
                obra_id=obra.id
            )
        )

    vinculos = UsuarioObra.query.filter_by(
        obra_id=obra.id
    ).order_by(
        UsuarioObra.criado_em.asc()
    ).all()

    return render_template(
        "equipe_obra.html",
        obra=obra,
        usuarios=usuarios,
        vinculos=vinculos,
    )


@app.route(
    "/obras/<int:obra_id>/equipe/<int:vinculo_id>/remover",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def remover_equipe_obra(
    obra_id,
    vinculo_id
):

    obra = obter_obra(
        obra_id
    )

    if not obra:

        flash(
            "Obra não encontrada.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if obra.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    vinculo = db.session.get(
        UsuarioObra,
        vinculo_id
    )

    if not vinculo:

        flash(
            "Vínculo não encontrado.",
            "danger"
        )

        return redirect(
            url_for(
                "equipe_obra",
                obra_id=obra.id
            )
        )

    if vinculo.obra_id != obra.id:

        flash(
            "O funcionário não pertence a esta obra.",
            "danger"
        )

        return redirect(
            url_for(
                "equipe_obra",
                obra_id=obra.id
            )
        )

    try:

        db.session.delete(
            vinculo
        )

        db.session.commit()

        flash(
            "Funcionário removido da obra.",
            "success"
        )

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao remover funcionário da obra"
        )

        flash(
            "Não foi possível remover o funcionário.",
            "danger"
        )

    return redirect(
        url_for(
            "equipe_obra",
            obra_id=obra.id
        )
    )


# ============================================================
# CATÁLOGO DE MATERIAIS
# ============================================================

MATERIAIS_CATALOGO = [

    # --------------------------------------------------------
    # AGREGADOS
    # --------------------------------------------------------

    {
        "nome": "Areia média",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Areia média para argamassas e concreto."
    },

    {
        "nome": "Areia grossa",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Areia grossa para concreto e serviços diversos."
    },

    {
        "nome": "Areia fina",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Areia fina para acabamento e argamassas."
    },

    {
        "nome": "Brita 0",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Brita zero para concreto e serviços de construção."
    },

    {
        "nome": "Brita 1",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Brita um para produção de concreto."
    },

    {
        "nome": "Brita 2",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Brita dois para concreto e fundações."
    },

    {
        "nome": "Pedra de mão",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Pedra de mão para fundações e contenções."
    },

    {
        "nome": "Pedrisco",
        "categoria": "Agregados",
        "unidade": "m³",
        "descricao": "Pedrisco para concreto e pavimentação."
    },

    # --------------------------------------------------------
    # CIMENTO E ARGAMASSAS
    # --------------------------------------------------------

    {
        "nome": "Cimento CP II 32",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Cimento Portland CP II 32."
    },

    {
        "nome": "Cimento CP II 40",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Cimento Portland CP II 40."
    },

    {
        "nome": "Cimento CP III",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Cimento Portland CP III."
    },

    {
        "nome": "Cal hidratada",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Cal hidratada para argamassas."
    },

    {
        "nome": "Argamassa AC-I",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Argamassa colante para áreas internas."
    },

    {
        "nome": "Argamassa AC-II",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Argamassa colante para áreas internas e externas."
    },

    {
        "nome": "Argamassa AC-III",
        "categoria": "Cimento e argamassas",
        "unidade": "saco",
        "descricao": "Argamassa colante de maior desempenho."
    },

    {
        "nome": "Rejunte cimentício",
        "categoria": "Cimento e argamassas",
        "unidade": "kg",
        "descricao": "Rejunte para pisos e revestimentos."
    },

    {
        "nome": "Rejunte acrílico",
        "categoria": "Cimento e argamassas",
        "unidade": "kg",
        "descricao": "Rejunte acrílico para acabamento."
    },

    # --------------------------------------------------------
    # CONCRETO
    # --------------------------------------------------------

    {
        "nome": "Concreto usinado",
        "categoria": "Concreto",
        "unidade": "m³",
        "descricao": "Concreto usinado para estruturas."
    },

    {
        "nome": "Aditivo plastificante",
        "categoria": "Concreto",
        "unidade": "L",
        "descricao": "Aditivo plastificante para concreto e argamassa."
    },

    {
        "nome": "Aditivo impermeabilizante",
        "categoria": "Concreto",
        "unidade": "L",
        "descricao": "Aditivo para melhorar a impermeabilidade."
    },

    {
        "nome": "Fibra para concreto",
        "categoria": "Concreto",
        "unidade": "kg",
        "descricao": "Fibra para reforço de concreto."
    },

    # --------------------------------------------------------
    # ALVENARIA
    # --------------------------------------------------------

    {
        "nome": "Bloco cerâmico 9 cm",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Bloco cerâmico para vedação."
    },

    {
        "nome": "Bloco cerâmico 11,5 cm",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Bloco cerâmico para alvenaria."
    },

    {
        "nome": "Bloco cerâmico 14 cm",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Bloco cerâmico para vedação."
    },

    {
        "nome": "Bloco de concreto",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Bloco de concreto para alvenaria."
    },

    {
        "nome": "Tijolo maciço",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Tijolo cerâmico maciço."
    },

    {
        "nome": "Canaleta cerâmica",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Canaleta cerâmica para vergas e cintas."
    },

    {
        "nome": "Canaleta de concreto",
        "categoria": "Alvenaria",
        "unidade": "un",
        "descricao": "Canaleta de concreto para cintas."
    },

    # --------------------------------------------------------
    # AÇO E FERRAGENS
    # --------------------------------------------------------

    {
        "nome": "Vergalhão CA-50 4,2 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 5 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 6,3 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 8 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 10 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 12,5 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Vergalhão CA-50 16 mm",
        "categoria": "Aço e ferragens",
        "unidade": "barra",
        "descricao": "Vergalhão CA-50 para armaduras."
    },

    {
        "nome": "Arame recozido",
        "categoria": "Aço e ferragens",
        "unidade": "kg",
        "descricao": "Arame recozido para amarração de ferragens."
    },

    {
        "nome": "Tela soldada",
        "categoria": "Aço e ferragens",
        "unidade": "m²",
        "descricao": "Tela soldada para reforço."
    },

    {
        "nome": "Estribo pronto",
        "categoria": "Aço e ferragens",
        "unidade": "un",
        "descricao": "Estribo para armação de estruturas."
    },

    {
        "nome": "Prego 17 x 27",
        "categoria": "Aço e ferragens",
        "unidade": "kg",
        "descricao": "Prego para uso geral em construção."
    },

    {
        "nome": "Prego 18 x 27",
        "categoria": "Aço e ferragens",
        "unidade": "kg",
        "descricao": "Prego para uso geral."
    },

    {
        "nome": "Prego 19 x 36",
        "categoria": "Aço e ferragens",
        "unidade": "kg",
        "descricao": "Prego para madeira e formas."
    },

    # --------------------------------------------------------
    # MADEIRA
    # --------------------------------------------------------

    {
        "nome": "Tábua de pinus",
        "categoria": "Madeira",
        "unidade": "m",
        "descricao": "Tábua de madeira para formas e serviços gerais."
    },

    {
        "nome": "Sarrafo de madeira",
        "categoria": "Madeira",
        "unidade": "m",
        "descricao": "Sarrafo para formas e estrutura auxiliar."
    },

    {
        "nome": "Caibro de madeira",
        "categoria": "Madeira",
        "unidade": "m",
        "descricao": "Caibro para estruturas e cobertura."
    },

    {
        "nome": "Viga de madeira",
        "categoria": "Madeira",
        "unidade": "m",
        "descricao": "Viga de madeira para estrutura."
    },

    {
        "nome": "Compensado de madeira",
        "categoria": "Madeira",
        "unidade": "chapa",
        "descricao": "Chapa de compensado para formas."
    },

    # --------------------------------------------------------
    # IMPERMEABILIZAÇÃO
    # --------------------------------------------------------

    {
        "nome": "Manta asfáltica",
        "categoria": "Impermeabilização",
        "unidade": "m²",
        "descricao": "Manta asfáltica para impermeabilização."
    },

    {
        "nome": "Impermeabilizante líquido",
        "categoria": "Impermeabilização",
        "unidade": "L",
        "descricao": "Impermeabilizante líquido."
    },

    {
        "nome": "Argamassa impermeabilizante",
        "categoria": "Impermeabilização",
        "unidade": "kg",
        "descricao": "Argamassa para impermeabilização."
    },

    {
        "nome": "Primer para manta",
        "categoria": "Impermeabilização",
        "unidade": "L",
        "descricao": "Primer para preparação da superfície."
    },

    # --------------------------------------------------------
    # HIDRÁULICA
    # --------------------------------------------------------

    {
        "nome": "Tubo PVC soldável 20 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para água fria."
    },

    {
        "nome": "Tubo PVC soldável 25 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para água fria."
    },

    {
        "nome": "Tubo PVC soldável 32 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para água fria."
    },

    {
        "nome": "Tubo PVC soldável 40 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para água fria."
    },

    {
        "nome": "Tubo PVC esgoto 40 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para esgoto."
    },

    {
        "nome": "Tubo PVC esgoto 50 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para esgoto."
    },

    {
        "nome": "Tubo PVC esgoto 75 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para esgoto."
    },

    {
        "nome": "Tubo PVC esgoto 100 mm",
        "categoria": "Hidráulica",
        "unidade": "barra",
        "descricao": "Tubo PVC para esgoto."
    },

    {
        "nome": "Joelho PVC 90° 20 mm",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Conexão PVC soldável."
    },

    {
        "nome": "Joelho PVC 90° 25 mm",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Conexão PVC soldável."
    },

    {
        "nome": "Joelho PVC 90° 32 mm",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Conexão PVC soldável."
    },

    {
        "nome": "Tê PVC 20 mm",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Conexão hidráulica PVC."
    },

    {
        "nome": "Tê PVC 25 mm",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Conexão hidráulica PVC."
    },

    {
        "nome": "Registro de gaveta",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Registro hidráulico."
    },

    {
        "nome": "Registro de pressão",
        "categoria": "Hidráulica",
        "unidade": "un",
        "descricao": "Registro de pressão."
    },

    # --------------------------------------------------------
    # ELÉTRICA
    # --------------------------------------------------------

    {
        "nome": "Fio 1,5 mm²",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Condutor elétrico para circuitos."
    },

    {
        "nome": "Fio 2,5 mm²",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Condutor elétrico para circuitos."
    },

    {
        "nome": "Fio 4 mm²",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Condutor elétrico."
    },

    {
        "nome": "Fio 6 mm²",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Condutor elétrico."
    },

    {
        "nome": "Cabo flexível 10 mm²",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Cabo flexível para instalações elétricas."
    },

    {
        "nome": "Eletroduto corrugado 20 mm",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Eletroduto corrugado para instalações."
    },

    {
        "nome": "Eletroduto corrugado 25 mm",
        "categoria": "Elétrica",
        "unidade": "m",
        "descricao": "Eletroduto corrugado para instalações."
    },

    {
        "nome": "Caixa 4x2",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Caixa de embutir para instalações elétricas."
    },

    {
        "nome": "Caixa 4x4",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Caixa de embutir para instalações elétricas."
    },

    {
        "nome": "Disjuntor 10 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Disjuntor termomagnético."
    },

    {
        "nome": "Disjuntor 16 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Disjuntor termomagnético."
    },

    {
        "nome": "Disjuntor 20 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Disjuntor termomagnético."
    },

    {
        "nome": "Disjuntor 25 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Disjuntor termomagnético."
    },

    {
        "nome": "Disjuntor 32 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Disjuntor termomagnético."
    },

    {
        "nome": "Tomada 10 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Tomada elétrica."
    },

    {
        "nome": "Tomada 20 A",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Tomada elétrica."
    },

    {
        "nome": "Interruptor simples",
        "categoria": "Elétrica",
        "unidade": "un",
        "descricao": "Interruptor simples."
    },

    # --------------------------------------------------------
    # PISOS E REVESTIMENTOS
    # --------------------------------------------------------

    {
        "nome": "Piso cerâmico",
        "categoria": "Pisos e revestimentos",
        "unidade": "m²",
        "descricao": "Piso cerâmico para áreas internas e externas."
    },

    {
        "nome": "Porcelanato",
        "categoria": "Pisos e revestimentos",
        "unidade": "m²",
        "descricao": "Porcelanato para revestimento."
    },

    {
        "nome": "Azulejo cerâmico",
        "categoria": "Pisos e revestimentos",
        "unidade": "m²",
        "descricao": "Revestimento cerâmico para paredes."
    },

    {
        "nome": "Rodapé cerâmico",
        "categoria": "Pisos e revestimentos",
        "unidade": "m",
        "descricao": "Rodapé para acabamento."
    },

    # --------------------------------------------------------
    # PINTURA
    # --------------------------------------------------------

    {
        "nome": "Tinta acrílica branca",
        "categoria": "Pintura",
        "unidade": "L",
        "descricao": "Tinta acrílica para paredes."
    },

    {
        "nome": "Tinta látex",
        "categoria": "Pintura",
        "unidade": "L",
        "descricao": "Tinta látex para áreas internas."
    },

    {
        "nome": "Selador acrílico",
        "categoria": "Pintura",
        "unidade": "L",
        "descricao": "Selador para preparação de paredes."
    },

    {
        "nome": "Massa corrida",
        "categoria": "Pintura",
        "unidade": "kg",
        "descricao": "Massa para regularização e acabamento."
    },

    {
        "nome": "Massa acrílica",
        "categoria": "Pintura",
        "unidade": "kg",
        "descricao": "Massa acrílica para áreas internas e externas."
    },

    {
        "nome": "Fundo preparador",
        "categoria": "Pintura",
        "unidade": "L",
        "descricao": "Fundo preparador de paredes."
    },

    {
        "nome": "Thinner",
        "categoria": "Pintura",
        "unidade": "L",
        "descricao": "Solvente para limpeza e diluição conforme especificação."
    },

    # --------------------------------------------------------
    # FIXAÇÃO
    # --------------------------------------------------------

    {
        "nome": "Parafuso para madeira",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Parafuso para madeira."
    },

    {
        "nome": "Parafuso para drywall",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Parafuso para drywall."
    },

    {
        "nome": "Parafuso sextavado",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Parafuso sextavado."
    },

    {
        "nome": "Bucha 6 mm",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Bucha de nylon 6 mm."
    },

    {
        "nome": "Bucha 8 mm",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Bucha de nylon 8 mm."
    },

    {
        "nome": "Bucha 10 mm",
        "categoria": "Fixação",
        "unidade": "un",
        "descricao": "Bucha de nylon 10 mm."
    },

    # --------------------------------------------------------
    # EPI
    # --------------------------------------------------------

    {
        "nome": "Capacete de segurança",
        "categoria": "EPIs",
        "unidade": "un",
        "descricao": "Capacete de proteção individual."
    },

    {
        "nome": "Óculos de proteção",
        "categoria": "EPIs",
        "unidade": "un",
        "descricao": "Óculos de segurança."
    },

    {
        "nome": "Luva de proteção",
        "categoria": "EPIs",
        "unidade": "par",
        "descricao": "Luva de proteção para atividades de obra."
    },

    {
        "nome": "Protetor auricular",
        "categoria": "EPIs",
        "unidade": "un",
        "descricao": "Protetor auricular."
    },

    {
        "nome": "Máscara PFF2",
        "categoria": "EPIs",
        "unidade": "un",
        "descricao": "Respirador PFF2."
    },

    {
        "nome": "Cinto de segurança tipo paraquedista",
        "categoria": "EPIs",
        "unidade": "un",
        "descricao": "Equipamento para proteção contra quedas."
    },

    {
        "nome": "Botina de segurança",
        "categoria": "EPIs",
        "unidade": "par",
        "descricao": "Calçado de segurança."
    },

]


# ============================================================
# FUNÇÕES DO CATÁLOGO
# ============================================================

def normalizar_texto_catalogo(valor):

    valor = str(
        valor or ""
    ).strip().lower()

    valor = unicodedata.normalize(
        "NFKD",
        valor
    )

    return "".join(
        caractere
        for caractere in valor
        if not unicodedata.combining(
            caractere
        )
    )


def dados_material_catalogo():

    return [
        {
            "nome": item["nome"],
            "categoria": item["categoria"],
            "unidade": item["unidade"],
            "descricao": item.get(
                "descricao",
                ""
            ),
        }
        for item in MATERIAIS_CATALOGO
    ]


def material_catalogo_por_nome(nome):

    alvo = normalizar_texto_catalogo(
        nome
    )

    for item in MATERIAIS_CATALOGO:

        if normalizar_texto_catalogo(
            item["nome"]
        ) == alvo:

            return item

    return None


def catalogo_materiais_por_categoria():

    categorias = {}

    for item in MATERIAIS_CATALOGO:

        categoria = item["categoria"]

        categorias.setdefault(
            categoria,
            []
        ).append(
            item
        )

    return categorias


@app.context_processor
def contexto_catalogo():

    return {
        "catalogo_materiais": dados_material_catalogo(),
        "catalogo_materiais_categorias":
            catalogo_materiais_por_categoria(),
    }


# ============================================================
# MATERIAIS
# ============================================================

@app.route(
    "/materiais"
)
@empresa_acesso_obrigatorio
def materiais():

    empresa = empresa_usuario_atual()

    lista = Material.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    return render_template(
        "materiais.html",
        materiais=lista,
        empresa=empresa,
    )


@app.route(
    "/materiais/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def novo_material():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("empresa_dashboard")
        )

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        catalogo = material_catalogo_por_nome(
            nome
        )

        if catalogo:

            categoria = catalogo["categoria"]

            unidade = catalogo["unidade"]

            descricao = catalogo.get(
                "descricao",
                ""
            )

        else:

            categoria = (
                request.form.get("categoria")
                or "Outros"
            ).strip()

            unidade = (
                request.form.get("unidade")
                or "un"
            ).strip()

            descricao = (
                request.form.get("descricao")
                or ""
            ).strip()

        if not nome:

            flash(
                "Informe o nome do material.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=None,
                empresa=empresa,
                catalogo_materiais=dados_material_catalogo(),
                titulo="Novo material"
            )

        try:

            estoque_minimo = float(
                request.form.get(
                    "estoque_minimo",
                    0
                ) or 0
            )

        except (
            ValueError,
            TypeError
        ):

            estoque_minimo = 0

        material = Material(
            empresa_id=empresa.id,
            categoria=categoria,
            nome=nome,
            descricao=descricao,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=0,
            ativo=True,
        )

        db.session.add(
            material
        )

        try:

            db.session.commit()

            flash(
                "Material cadastrado com sucesso.",
                "success"
            )

            return redirect(
                url_for("materiais")
            )

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao cadastrar material"
            )

            flash(
                "Não foi possível cadastrar o material.",
                "danger"
            )

    return render_template(
        "material_form.html",
        material=None,
        empresa=empresa,
        catalogo_materiais=dados_material_catalogo(),
        titulo="Novo material"
    )


@app.route(
    "/materiais/<int:material_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_material(material_id):

    material = obter_material(
        material_id
    )

    if not material:

        flash(
            "Material não encontrado.",
            "danger"
        )

        return redirect(
            url_for("materiais")
        )

    if material.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a este material.",
            "danger"
        )

        return redirect(
            url_for("materiais")
        )

    empresa = empresa_usuario_atual()

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        if not nome:

            flash(
                "O nome do material é obrigatório.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=material,
                empresa=empresa,
                catalogo_materiais=dados_material_catalogo(),
                titulo="Editar material"
            )

        catalogo = material_catalogo_por_nome(
            nome
        )

        material.nome = nome

        if catalogo:

            material.categoria = (
                catalogo["categoria"]
            )

            material.unidade = (
                catalogo["unidade"]
            )

            material.descricao = (
                catalogo.get(
                    "descricao",
                    ""
                )
            )

        else:

            material.categoria = (
                request.form.get("categoria")
                or material.categoria
            ).strip()

            material.unidade = (
                request.form.get("unidade")
                or material.unidade
            ).strip()

            material.descricao = (
                request.form.get("descricao")
                or ""
            ).strip()

        try:

            material.estoque_minimo = float(
                request.form.get(
                    "estoque_minimo",
                    material.estoque_minimo or 0
                ) or 0
            )

        except (
            ValueError,
            TypeError
        ):

            pass

        try:

            db.session.commit()

            flash(
                "Material atualizado com sucesso.",
                "success"
            )

            return redirect(
                url_for("materiais")
            )

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar material"
            )

            flash(
                "Não foi possível atualizar o material.",
                "danger"
            )

    return render_template(
        "material_form.html",
        material=material,
        empresa=empresa,
        catalogo_materiais=dados_material_catalogo(),
        titulo="Editar material"
    )


@app.route(
    "/materiais/<int:material_id>/alternar-status",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def alternar_status_material(material_id):

    material = obter_material(
        material_id
    )

    if not material:

        flash(
            "Material não encontrado.",
            "danger"
        )

        return redirect(
            url_for("materiais")
        )

    if material.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a este material.",
            "danger"
        )

        return redirect(
            url_for("materiais")
        )

    material.ativo = not material.ativo

    try:

        db.session.commit()

        flash(
            "Status do material atualizado.",
            "success"
        )

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status do material"
        )

        flash(
            "Não foi possível alterar o status.",
            "danger"
        )

    return redirect(
        url_for("materiais")
    )
    # ============================================================
# SOLICITAÇÕES
# ============================================================

@app.route("/solicitacoes")
@empresa_acesso_obrigatorio
def solicitacoes():

    if eh_administrador_empresa():

        lista = Solicitacao.query.join(
            Obra,
            Solicitacao.obra_id == Obra.id
        ).filter(
            Obra.empresa_id == current_user.empresa_id
        ).order_by(
            Solicitacao.criado_em.desc()
        ).all()

    else:

        obra_ids = [
            obra.id
            for obra in obras_do_usuario()
        ]

        if not obra_ids:
            lista = []
        else:
            lista = Solicitacao.query.filter(
                Solicitacao.obra_id.in_(obra_ids)
            ).order_by(
                Solicitacao.criado_em.desc()
            ).all()

    return render_template(
        "solicitacoes.html",
        solicitacoes=lista
    )


# ============================================================
# NOVA SOLICITAÇÃO
# ============================================================

@app.route(
    "/solicitacoes/nova",
    methods=["GET", "POST"]
)
@empresa_acesso_obrigatorio
def nova_solicitacao():

    empresa_id = current_user.empresa_id

    obras_disponiveis = obras_do_usuario()

    materiais_lista = Material.query.filter_by(
        empresa_id=empresa_id,
        ativo=True
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    ferramentas_lista = Ferramenta.query.filter_by(
        empresa_id=empresa_id,
        ativo=True
    ).order_by(
        Ferramenta.categoria.asc(),
        Ferramenta.nome.asc()
    ).all()

    if request.method == "POST":

        try:
            obra_id = int(
                request.form.get("obra_id")
            )
        except (
            ValueError,
            TypeError
        ):
            obra_id = None

        tipo = (
            request.form.get("tipo_recurso")
            or request.form.get("tipo")
            or "material"
        ).strip().lower()

        recurso_id = request.form.get(
            "recurso_id"
        )

        recurso_nome = (
            request.form.get("recurso_nome")
            or ""
        ).strip()

        observacao = (
            request.form.get("observacao")
            or ""
        ).strip()

        try:
            quantidade = float(
                request.form.get(
                    "quantidade",
                    0
                )
                or 0
            )
        except (
            ValueError,
            TypeError
        ):
            quantidade = 0

        if tipo not in (
            "material",
            "ferramenta",
            "outro"
        ):
            flash(
                "Tipo de solicitação inválido.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        obra = None

        if obra_id:
            obra = db.session.get(
                Obra,
                obra_id
            )

        if not obra:
            flash(
                "Selecione uma obra válida.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if obra.empresa_id != empresa_id:
            flash(
                "A obra selecionada não pertence à sua empreiteira.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if not usuario_tem_acesso_obra(obra):
            flash(
                "Você não possui acesso a esta obra.",
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

        nova = Solicitacao(
            obra_id=obra.id,
            usuario_id=current_user.id,
            quantidade=quantidade,
            observacao=observacao,
            status="pendente",
            tipo_recurso=tipo,
            recurso_nome=recurso_nome or None,
        )

        # ----------------------------------------------------
        # MATERIAL
        # ----------------------------------------------------

        if tipo == "material":

            if not recurso_id:
                flash(
                    "Selecione um material.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            try:
                recurso_id = int(recurso_id)
            except (
                ValueError,
                TypeError
            ):
                flash(
                    "Material inválido.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            material = db.session.get(
                Material,
                recurso_id
            )

            if (
                not material
                or not material.ativo
                or material.empresa_id != empresa_id
            ):
                flash(
                    "Material não encontrado.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            nova.material_id = material.id
            nova.ferramenta_id = None
            nova.recurso_nome = material.nome

        # ----------------------------------------------------
        # FERRAMENTA
        # ----------------------------------------------------

        elif tipo == "ferramenta":

            if not recurso_id:
                flash(
                    "Selecione uma ferramenta.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            try:
                recurso_id = int(recurso_id)
            except (
                ValueError,
                TypeError
            ):
                flash(
                    "Ferramenta inválida.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            ferramenta = db.session.get(
                Ferramenta,
                recurso_id
            )

            if (
                not ferramenta
                or not ferramenta.ativo
                or ferramenta.empresa_id != empresa_id
            ):
                flash(
                    "Ferramenta não encontrada.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            nova.ferramenta_id = ferramenta.id
            nova.material_id = None
            nova.recurso_nome = ferramenta.nome

        # ----------------------------------------------------
        # OUTRO
        # ----------------------------------------------------

        else:

            if not recurso_nome:
                flash(
                    "Informe o nome do recurso solicitado.",
                    "danger"
                )

                return redirect(
                    url_for("nova_solicitacao")
                )

            nova.material_id = None
            nova.ferramenta_id = None

        db.session.add(nova)

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao criar solicitação"
            )

            flash(
                "Não foi possível enviar a solicitação.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        flash(
            "Solicitação enviada para aprovação.",
            "success"
        )

        return redirect(
            url_for("solicitacoes")
        )

    return render_template(
        "solicitacao_form.html",
        obras=obras_disponiveis,
        materiais=materiais_lista,
        ferramentas=ferramentas_lista,
        tipos_solicitacao=TIPOS_SOLICITACAO,
    )


# ============================================================
# MARCAR SOLICITAÇÃO COMO COMPRADA
# ============================================================

@app.route(
    "/solicitacoes/<int:solicitacao_id>/comprado",
    methods=["POST"]
)
@compras_obrigatorio
def marcar_solicitacao_comprada(
    solicitacao_id
):

    solicitacao = db.session.get(
        Solicitacao,
        solicitacao_id
    )

    if not solicitacao:
        flash(
            "Solicitação não encontrada.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    obra = obter_obra(
        solicitacao.obra_id
    )

    if (
        not obra
        or not usuario_pode_gerenciar_obra(obra)
    ):
        flash(
            "Você não possui permissão para esta solicitação.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "confirmado":
        flash(
            "Esta solicitação já foi confirmada.",
            "info"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "cancelado":
        flash(
            "Esta solicitação está cancelada.",
            "warning"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "comprado":
        flash(
            "Esta solicitação já está marcada como comprada.",
            "info"
        )

        return redirect(
            url_for("solicitacoes")
        )

    solicitacao.status = "comprado"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao marcar solicitação como comprada"
        )

        flash(
            "Não foi possível atualizar a solicitação.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    flash(
        "Solicitação marcada como comprada. "
        "Agora aguarda a confirmação da entrada no estoque.",
        "success"
    )

    return redirect(
        url_for("solicitacoes")
    )


# ============================================================
# CONFIRMAR ENTRADA NO ESTOQUE
# ============================================================

@app.route(
    "/solicitacoes/<int:solicitacao_id>/confirmar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def confirmar_solicitacao(
    solicitacao_id
):

    solicitacao = db.session.get(
        Solicitacao,
        solicitacao_id
    )

    if not solicitacao:

        flash(
            "Solicitação não encontrada.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    obra = obter_obra(
        solicitacao.obra_id
    )

    if not obra:

        flash(
            "A obra desta solicitação não existe.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if obra.empresa_id != current_user.empresa_id:

        flash(
            "Esta solicitação pertence a outra empreiteira.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    # --------------------------------------------------------
    # IDEMPOTÊNCIA
    # Não permite adicionar o mesmo item duas vezes.
    # --------------------------------------------------------

    if solicitacao.status == "confirmado":

        flash(
            "Esta solicitação já foi confirmada "
            "e o estoque já foi atualizado.",
            "info"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "cancelado":

        flash(
            "Uma solicitação cancelada não pode ser confirmada.",
            "warning"
        )

        return redirect(
            url_for("solicitacoes")
        )

    # --------------------------------------------------------
    # MATERIAL
    # --------------------------------------------------------

    if solicitacao.tipo_recurso == "material" or solicitacao.material_id:

        if not solicitacao.material_id:

            flash(
                "A solicitação não possui material vinculado.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        material = db.session.get(
            Material,
            solicitacao.material_id
        )

        if (
            not material
            or material.empresa_id != current_user.empresa_id
        ):

            flash(
                "O material solicitado não pertence "
                "à empreiteira desta obra.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        material.estoque_atual = (
            float(material.estoque_atual or 0)
            + float(solicitacao.quantidade or 0)
        )

    # --------------------------------------------------------
    # FERRAMENTA
    # --------------------------------------------------------

    elif (
        solicitacao.tipo_recurso == "ferramenta"
        or solicitacao.ferramenta_id
    ):

        if not solicitacao.ferramenta_id:

            flash(
                "A solicitação não possui ferramenta vinculada.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        ferramenta = db.session.get(
            Ferramenta,
            solicitacao.ferramenta_id
        )

        if (
            not ferramenta
            or ferramenta.empresa_id != current_user.empresa_id
        ):

            flash(
                "A ferramenta solicitada não pertence "
                "à empreiteira desta obra.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        ferramenta.estoque_atual = (
            float(ferramenta.estoque_atual or 0)
            + float(solicitacao.quantidade or 0)
        )

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    elif solicitacao.tipo_recurso == "outro":

        # Recurso genérico não altera estoque.
        pass

    else:

        flash(
            "Tipo de solicitação inválido.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    solicitacao.status = "confirmado"

    solicitacao.confirmado_por_id = (
        current_user.id
    )

    solicitacao.confirmado_em = (
        datetime.utcnow()
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao confirmar solicitação"
        )

        flash(
            "Não foi possível confirmar a entrada.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    flash(
        "Compra confirmada e estoque atualizado com sucesso.",
        "success"
    )

    return redirect(
        url_for("solicitacoes")
    )


# ============================================================
# CANCELAR SOLICITAÇÃO
# ============================================================

@app.route(
    "/solicitacoes/<int:solicitacao_id>/cancelar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def cancelar_solicitacao(
    solicitacao_id
):

    solicitacao = db.session.get(
        Solicitacao,
        solicitacao_id
    )

    if not solicitacao:

        flash(
            "Solicitação não encontrada.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    obra = obter_obra(
        solicitacao.obra_id
    )

    if (
        not obra
        or obra.empresa_id != current_user.empresa_id
    ):

        flash(
            "Você não possui permissão para esta solicitação.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "confirmado":

        flash(
            "Uma solicitação já confirmada não pode ser cancelada.",
            "warning"
        )

        return redirect(
            url_for("solicitacoes")
        )

    if solicitacao.status == "cancelado":

        flash(
            "Esta solicitação já está cancelada.",
            "info"
        )

        return redirect(
            url_for("solicitacoes")
        )

    solicitacao.status = "cancelado"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao cancelar solicitação"
        )

        flash(
            "Não foi possível cancelar a solicitação.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    flash(
        "Solicitação cancelada com sucesso.",
        "success"
    )

    return redirect(
        url_for("solicitacoes")
    )
    # ============================================================
# ESTOQUE — VISÃO GERAL
# ============================================================

@app.route("/estoque")
@estoque_obrigatorio
def estoque():

    empresa_id = current_user.empresa_id

    materiais = Material.query.filter_by(
        empresa_id=empresa_id,
        ativo=True
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    ferramentas_lista = Ferramenta.query.filter_by(
        empresa_id=empresa_id,
        ativo=True
    ).order_by(
        Ferramenta.categoria.asc(),
        Ferramenta.nome.asc()
    ).all()

    total_materiais = len(materiais)
    total_ferramentas = len(ferramentas_lista)

    materiais_baixos = [
        material
        for material in materiais
        if float(material.estoque_atual or 0)
        <= float(material.estoque_minimo or 0)
    ]

    ferramentas_baixas = [
        ferramenta
        for ferramenta in ferramentas_lista
        if float(ferramenta.estoque_atual or 0)
        <= float(ferramenta.estoque_minimo or 0)
    ]

    return render_template(
        "estoque.html",
        materiais=materiais,
        ferramentas=ferramentas_lista,
        total_materiais=total_materiais,
        total_ferramentas=total_ferramentas,
        materiais_baixos=materiais_baixos,
        ferramentas_baixas=ferramentas_baixas,
    )


# ============================================================
# FERRAMENTAS
# ============================================================

@app.route("/ferramentas")
@estoque_obrigatorio
def ferramentas():

    ferramentas_lista = Ferramenta.query.filter_by(
        empresa_id=current_user.empresa_id,
        ativo=True
    ).order_by(
        Ferramenta.categoria.asc(),
        Ferramenta.nome.asc()
    ).all()

    return render_template(
        "ferramentas.html",
        ferramentas=ferramentas_lista
    )


# ============================================================
# NOVA FERRAMENTA
# ============================================================

@app.route(
    "/ferramentas/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def nova_ferramenta():

    if request.method == "POST":

        categoria = (
            request.form.get("categoria")
            or ""
        ).strip()

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        descricao = (
            request.form.get("descricao")
            or ""
        ).strip()

        unidade = (
            request.form.get("unidade")
            or "un"
        ).strip()

        try:

            estoque_minimo = float(
                request.form.get(
                    "estoque_minimo",
                    0
                )
                or 0
            )

            estoque_atual = float(
                request.form.get(
                    "estoque_atual",
                    0
                )
                or 0
            )

        except (
            ValueError,
            TypeError
        ):

            flash(
                "Os valores de estoque são inválidos.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=None,
                titulo="Nova ferramenta"
            )

        if estoque_minimo < 0:
            estoque_minimo = 0

        if estoque_atual < 0:
            estoque_atual = 0

        if not categoria or not nome:

            flash(
                "Categoria e nome são obrigatórios.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=None,
                titulo="Nova ferramenta"
            )

        ferramenta = Ferramenta(
            empresa_id=current_user.empresa_id,
            categoria=categoria,
            nome=nome,
            descricao=descricao,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual,
            ativo=True,
        )

        db.session.add(ferramenta)

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao cadastrar ferramenta"
            )

            flash(
                "Não foi possível cadastrar a ferramenta.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=None,
                titulo="Nova ferramenta"
            )

        flash(
            "Ferramenta cadastrada com sucesso.",
            "success"
        )

        return redirect(
            url_for("ferramentas")
        )

    return render_template(
        "ferramenta_form.html",
        ferramenta=None,
        titulo="Nova ferramenta"
    )


# ============================================================
# EDITAR FERRAMENTA
# ============================================================

@app.route(
    "/ferramentas/<int:ferramenta_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_ferramenta(ferramenta_id):

    ferramenta = db.session.get(
        Ferramenta,
        ferramenta_id
    )

    if not ferramenta:

        flash(
            "Ferramenta não encontrada.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    if ferramenta.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta ferramenta.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    if request.method == "POST":

        categoria = (
            request.form.get("categoria")
            or ""
        ).strip()

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        descricao = (
            request.form.get("descricao")
            or ""
        ).strip()

        unidade = (
            request.form.get("unidade")
            or "un"
        ).strip()

        try:

            estoque_minimo = float(
                request.form.get(
                    "estoque_minimo",
                    0
                )
                or 0
            )

            estoque_atual = float(
                request.form.get(
                    "estoque_atual",
                    0
                )
                or 0
            )

        except (
            ValueError,
            TypeError
        ):

            flash(
                "Os valores de estoque são inválidos.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta"
            )

        if not categoria or not nome:

            flash(
                "Categoria e nome são obrigatórios.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta"
            )

        ferramenta.categoria = categoria
        ferramenta.nome = nome
        ferramenta.descricao = descricao
        ferramenta.unidade = unidade
        ferramenta.estoque_minimo = max(
            0,
            estoque_minimo
        )
        ferramenta.estoque_atual = max(
            0,
            estoque_atual
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar ferramenta"
            )

            flash(
                "Não foi possível atualizar a ferramenta.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta"
            )

        flash(
            "Ferramenta atualizada com sucesso.",
            "success"
        )

        return redirect(
            url_for("ferramentas")
        )

    return render_template(
        "ferramenta_form.html",
        ferramenta=ferramenta,
        titulo="Editar ferramenta"
    )


# ============================================================
# ATIVAR / DESATIVAR FERRAMENTA
# ============================================================

@app.route(
    "/ferramentas/<int:ferramenta_id>/alternar-status",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def alternar_status_ferramenta(
    ferramenta_id
):

    ferramenta = db.session.get(
        Ferramenta,
        ferramenta_id
    )

    if not ferramenta:

        flash(
            "Ferramenta não encontrada.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    if ferramenta.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta ferramenta.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    ferramenta.ativo = not ferramenta.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status da ferramenta"
        )

        flash(
            "Não foi possível alterar o status.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    if ferramenta.ativo:

        flash(
            "Ferramenta ativada.",
            "success"
        )

    else:

        flash(
            "Ferramenta desativada.",
            "success"
        )

    return redirect(
        url_for("ferramentas")
    )


# ============================================================
# ENTRADA MANUAL DE MATERIAL
# ============================================================

@app.route(
    "/estoque/material/<int:material_id>/entrada",
    methods=["POST"]
)
@estoque_obrigatorio
def entrada_material(
    material_id
):

    material = db.session.get(
        Material,
        material_id
    )

    if not material:

        flash(
            "Material não encontrado.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if material.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a este material.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    try:

        quantidade = float(
            request.form.get(
                "quantidade",
                0
            )
            or 0
        )

    except (
        ValueError,
        TypeError
    ):

        quantidade = 0

    if quantidade <= 0:

        flash(
            "Informe uma quantidade maior que zero.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    material.estoque_atual = (
        float(material.estoque_atual or 0)
        + quantidade
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro na entrada manual de material"
        )

        flash(
            "Não foi possível registrar a entrada.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    flash(
        f"Entrada de {quantidade:g} "
        f"{material.unidade or 'un'} de "
        f"{material.nome} registrada.",
        "success"
    )

    return redirect(
        url_for("estoque")
    )


# ============================================================
# SAÍDA MANUAL DE MATERIAL
# ============================================================

@app.route(
    "/estoque/material/<int:material_id>/saida",
    methods=["POST"]
)
@estoque_obrigatorio
def saida_material(
    material_id
):

    material = db.session.get(
        Material,
        material_id
    )

    if not material:

        flash(
            "Material não encontrado.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if material.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a este material.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    try:

        quantidade = float(
            request.form.get(
                "quantidade",
                0
            )
            or 0
        )

    except (
        ValueError,
        TypeError
    ):

        quantidade = 0

    estoque_atual = float(
        material.estoque_atual or 0
    )

    if quantidade <= 0:

        flash(
            "Informe uma quantidade maior que zero.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if quantidade > estoque_atual:

        flash(
            "A saída não pode ser maior que o estoque disponível.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    material.estoque_atual = (
        estoque_atual - quantidade
    )
    # ============================================================
# SAÍDA MANUAL DE FERRAMENTA
# ============================================================

@app.route(
    "/estoque/ferramenta/<int:ferramenta_id>/saida",
    methods=["POST"]
)
@estoque_obrigatorio
def saida_ferramenta(
    ferramenta_id
):

    ferramenta = db.session.get(
        Ferramenta,
        ferramenta_id
    )

    if not ferramenta:

        flash(
            "Ferramenta não encontrada.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if ferramenta.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta ferramenta.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    try:

        quantidade = float(
            request.form.get(
                "quantidade",
                0
            )
            or 0
        )

    except (
        ValueError,
        TypeError
    ):

        quantidade = 0

    estoque_atual = float(
        ferramenta.estoque_atual or 0
    )

    if quantidade <= 0:

        flash(
            "Informe uma quantidade maior que zero.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if quantidade > estoque_atual:

        flash(
            "A saída não pode ser maior que "
            "a quantidade disponível.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    ferramenta.estoque_atual = (
        estoque_atual - quantidade
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro na saída manual de ferramenta"
        )

        flash(
            "Não foi possível registrar a saída.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    flash(
        f"Saída de {quantidade:g} "
        f"{ferramenta.unidade or 'un'} de "
        f"{ferramenta.nome} registrada.",
        "success"
    )

    return redirect(
        url_for("estoque")
    )


# ============================================================
# AJUSTE DE ESTOQUE DE MATERIAL
# ============================================================

@app.route(
    "/estoque/material/<int:material_id>/ajustar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def ajustar_estoque_material(
    material_id
):

    material = db.session.get(
        Material,
        material_id
    )

    if not material:

        flash(
            "Material não encontrado.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if material.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a este material.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    try:

        novo_estoque = float(
            request.form.get(
                "estoque_atual",
                0
            )
            or 0
        )

    except (
        ValueError,
        TypeError
    ):

        flash(
            "Quantidade de estoque inválida.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if novo_estoque < 0:

        flash(
            "O estoque não pode ser negativo.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    material.estoque_atual = novo_estoque

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao ajustar estoque de material"
        )

        flash(
            "Não foi possível ajustar o estoque.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    flash(
        f"Estoque de {material.nome} ajustado com sucesso.",
        "success"
    )

    return redirect(
        url_for("estoque")
    )


# ============================================================
# AJUSTE DE ESTOQUE DE FERRAMENTA
# ============================================================

@app.route(
    "/estoque/ferramenta/<int:ferramenta_id>/ajustar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def ajustar_estoque_ferramenta(
    ferramenta_id
):

    ferramenta = db.session.get(
        Ferramenta,
        ferramenta_id
    )

    if not ferramenta:

        flash(
            "Ferramenta não encontrada.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if ferramenta.empresa_id != current_user.empresa_id:

        flash(
            "Você não possui acesso a esta ferramenta.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    try:

        novo_estoque = float(
            request.form.get(
                "estoque_atual",
                0
            )
            or 0
        )

    except (
        ValueError,
        TypeError
    ):

        flash(
            "Quantidade de estoque inválida.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    if novo_estoque < 0:

        flash(
            "O estoque não pode ser negativo.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    ferramenta.estoque_atual = novo_estoque

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao ajustar estoque de ferramenta"
        )

        flash(
            "Não foi possível ajustar o estoque.",
            "danger"
        )

        return redirect(
            url_for("estoque")
        )

    flash(
        f"Estoque de {ferramenta.nome} ajustado com sucesso.",
        "success"
    )

    return redirect(
        url_for("estoque")
    )


# ============================================================
# PAINEL DA ADMINISTRAÇÃO DA EMPREITEIRA
# ============================================================

@app.route("/empresa/administracao")
@empresa_admin_obrigatorio
def empresa_administracao():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Usuario.nome.asc()
    ).all()

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.criado_em.desc()
    ).all()

    materiais = Material.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Material.nome.asc()
    ).all()

    ferramentas_lista = Ferramenta.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Ferramenta.nome.asc()
    ).all()

    solicitacoes_pendentes = Solicitacao.query.join(
        Obra,
        Solicitacao.obra_id == Obra.id
    ).filter(
        Obra.empresa_id == empresa.id,
        Solicitacao.status.in_([
            "pendente",
            "comprado",
        ])
    ).count()

    return render_template(
        "empresa_administracao.html",
        empresa=empresa,
        usuarios=usuarios,
        obras=obras,
        materiais=materiais,
        ferramentas=ferramentas_lista,
        solicitacoes_pendentes=solicitacoes_pendentes,
    )


# ============================================================
# COMPATIBILIDADE — PAINEL ADM
# ============================================================

@app.route(
    "/painel-adm",
    endpoint="admin"
)
@admin_obrigatorio
def admin_alias():

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
@login_obrigatorio
def logout():

    logout_user()

    flash(
        "Você saiu do sistema.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    return render_template(
        "404.html"
    ), 404


@app.errorhandler(403)
def acesso_negado(error):

    flash(
        "Você não possui permissão para acessar esta área.",
        "danger"
    )

    if current_user.is_authenticated:

        if eh_administrador():

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("empresa_dashboard")
        )

    return redirect(
        url_for("login")
    )


@app.errorhandler(500)
def erro_interno(error):

    try:
        db.session.rollback()
    except Exception:
        pass

    logging.exception(
        "Erro interno não tratado"
    )

    return render_template(
        "500.html"
    ), 500


# ============================================================
# INICIALIZAÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    inicializar_banco()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
