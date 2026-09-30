import os
import logging
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    session,
    make_response,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    current_user,
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)
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
    # Compatibilidade com URLs antigas do Render/PostgreSQL
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Fallback local
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///construtora_pro.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.login_message_category = "warning"


# ============================================================
# LOG
# ============================================================

logging.basicConfig(level=logging.INFO)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_cnpj(valor):
    """
    Remove pontos, barras, traços e qualquer caractere
    que não seja número.
    """
    if not valor:
        return ""

    return "".join(
        caractere
        for caractere in str(valor)
        if caractere.isdigit()
    )


def formatar_cnpj(cnpj):
    """
    Formata CNPJ para apresentação.
    """
    if not cnpj:
        return ""

    numeros = normalizar_cnpj(cnpj)

    if len(numeros) != 14:
        return cnpj

    return (
        f"{numeros[:2]}."
        f"{numeros[2:5]}."
        f"{numeros[5:8]}/"
        f"{numeros[8:12]}-"
        f"{numeros[12:]}"
    )


def empresa_nome(empresa):
    if not empresa:
        return ""

    return (
        empresa.nome_fantasia
        or empresa.razao_social
        or "Empresa"
    )


# ============================================================
# MODELOS
# ============================================================

class Empresa(db.Model):
    __tablename__ = "empresa"

    id = db.Column(db.Integer, primary_key=True)

    razao_social = db.Column(
        db.String(255),
        nullable=False
    )

    nome_fantasia = db.Column(
        db.String(255),
        nullable=True
    )

    cnpj = db.Column(
        db.String(14),
        unique=True,
        nullable=True
    )

    telefone = db.Column(
        db.String(50),
        nullable=True
    )

    email = db.Column(
        db.String(255),
        nullable=True
    )

    endereco = db.Column(
        db.String(500),
        nullable=True
    )

    ativo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
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


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nome = db.Column(
        db.String(255),
        nullable=False
    )

    usuario = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    senha_hash = db.Column(
        db.String(255),
        nullable=False
    )

    funcao = db.Column(
        db.String(50),
        default="funcionario",
        nullable=False
    )

    ativo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresa.id"),
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
    __tablename__ = "obra"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey("empresa.id"),
        nullable=False
    )

    nome = db.Column(
        db.String(255),
        nullable=False
    )

    cliente = db.Column(
        db.String(255),
        nullable=True
    )

    endereco = db.Column(
        db.String(500),
        nullable=True
    )

    responsavel = db.Column(
        db.String(255),
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
        db.String(50),
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
    __tablename__ = "material"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    categoria = db.Column(
        db.String(120),
        nullable=False
    )

    nome = db.Column(
        db.String(255),
        nullable=False
    )

    descricao = db.Column(
        db.Text,
        nullable=True
    )

    unidade = db.Column(
        db.String(50),
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
    __tablename__ = "solicitacao"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    obra_id = db.Column(
        db.Integer,
        db.ForeignKey("obra.id"),
        nullable=False
    )

    material_id = db.Column(
        db.Integer,
        db.ForeignKey("material.id"),
        nullable=False
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id"),
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
        db.String(50),
        default="pendente",
        nullable=False
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    obra = db.relationship(
        "Obra",
        backref=db.backref(
            "solicitacoes",
            lazy=True
        )
    )

    material = db.relationship(
        "Material",
        backref=db.backref(
            "solicitacoes",
            lazy=True
        )
    )

    usuario = db.relationship(
        "Usuario",
        backref=db.backref(
            "solicitacoes",
            lazy=True
        )
    )


# ============================================================
# LOGIN
# ============================================================

@login_manager.user_loader
def carregar_usuario(user_id):
    try:
        return db.session.get(
            Usuario,
            int(user_id)
        )
    except (TypeError, ValueError):
        return None


def usuario_atual():
    if not current_user.is_authenticated:
        return None

    return current_user


def eh_administrador():
    usuario = usuario_atual()

    if not usuario:
        return False

    return str(usuario.funcao).lower() == "adm"


def eh_administrador_empresa():
    usuario = usuario_atual()

    if not usuario:
        return False

    return str(usuario.funcao).lower() in [
        "administrador_empresa",
        "admin_empresa"
    ]


def empresa_usuario_atual():
    usuario = usuario_atual()

    if not usuario:
        return None

    if not usuario.empresa_id:
        return None

    return db.session.get(
        Empresa,
        usuario.empresa_id
    )


# ============================================================
# CONTEXT PROCESSOR
# ============================================================

@app.context_processor
def contexto_global():

    usuario = usuario_atual()
    empresa = empresa_usuario_atual()

    return {
        "usuario_logado": usuario,
        "usuario_eh_admin": eh_administrador(),
        "usuario_eh_admin_empresa": eh_administrador_empresa(),
        "empresa_usuario_logado": empresa,
        "current_year": datetime.now().year,
    }


# ============================================================
# DECORADORES
# ============================================================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:
            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        usuario = current_user

        if not usuario.ativo:
            logout_user()

            flash(
                "Seu usuário está inativo.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # ADM global não precisa estar vinculado a empresa
        if not eh_administrador():

            empresa = empresa_usuario_atual()

            if not empresa:
                logout_user()

                flash(
                    "Seu usuário não está vinculado a uma empresa ativa.",
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

            if not empresa.ativo:
                logout_user()

                flash(
                    "A empresa vinculada ao usuário está desativada.",
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

        return funcao(*args, **kwargs)

    return wrapper


def admin_obrigatorio(funcao):

    @wraps(funcao)
    @login_obrigatorio
    def wrapper(*args, **kwargs):

        if not eh_administrador():

            flash(
                "Acesso restrito ao administrador do sistema.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return funcao(*args, **kwargs)

    return wrapper


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:

        if eh_administrador():
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        usuario_login = (
            request.form.get("usuario") or ""
        ).strip().lower()

        senha = request.form.get("senha") or ""

        if not usuario_login or not senha:

            flash(
                "Informe usuário e senha.",
                "warning"
            )

            return render_template("login.html")

        usuario = Usuario.query.filter_by(
            usuario=usuario_login
        ).first()

        if not usuario or not usuario.verificar_senha(senha):

            flash(
                "Usuário ou senha inválidos.",
                "danger"
            )

            return render_template("login.html")

        if not usuario.ativo:

            flash(
                "Este usuário está desativado.",
                "danger"
            )

            return render_template("login.html")

        if not eh_administrador():

            empresa = empresa_usuario_atual()

            if not empresa or not empresa.ativo:

                flash(
                    "A empresa vinculada a este usuário está inativa ou não existe.",
                    "danger"
                )

                return render_template("login.html")

        login_user(
            usuario,
            remember=True
        )

        proxima = request.args.get("next")

        if proxima and proxima.startswith("/"):
            return redirect(proxima)

        if str(usuario.funcao).lower() == "adm":
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return render_template("login.html")


@app.route("/logout")
def logout():

    logout_user()

    flash(
        "Você saiu do sistema.",
        "info"
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# ADMIN - DASHBOARD
# ============================================================

@app.route("/admin")
@admin_obrigatorio
def admin_dashboard():

    empresas = Empresa.query.order_by(
        Empresa.id.desc()
    ).all()

    total_empresas = Empresa.query.count()

    empresas_ativas = Empresa.query.filter_by(
        ativo=True
    ).count()

    empresas_inativas = Empresa.query.filter_by(
        ativo=False
    ).count()

    total_usuarios = Usuario.query.count()

    total_obras = Obra.query.count()

    return render_template(
        "admin_dashboard.html",
        empresas=empresas,
        total_empresas=total_empresas,
        empresas_ativas=empresas_ativas,
        empresas_inativas=empresas_inativas,
        total_usuarios=total_usuarios,
        total_obras=total_obras,
    )


# ============================================================
# ADMIN - NOVA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/nova",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def admin_nova_empresa():

    titulo = "Nova empresa"

    if request.method == "GET":

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

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

    # --------------------------------------------
    # Validação
    # --------------------------------------------

    if not razao_social:

        flash(
            "A Razão Social é obrigatória.",
            "warning"
        )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

    if cnpj and len(cnpj) != 14:

        flash(
            "O CNPJ informado não possui 14 dígitos.",
            "warning"
        )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

    # --------------------------------------------
    # Verifica CNPJ duplicado
    # --------------------------------------------

    if cnpj:

        empresa_existente = Empresa.query.filter(
            Empresa.cnpj == cnpj
        ).first()

        if empresa_existente:

            flash(
                "Já existe uma empresa cadastrada com este CNPJ.",
                "warning"
            )

            return render_template(
                "empresa_form.html",
                empresa=None,
                titulo=titulo
            )

    # --------------------------------------------
    # Criação
    # --------------------------------------------

    empresa = Empresa(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia or None,
        cnpj=cnpj or None,
        telefone=telefone or None,
        email=email or None,
        endereco=endereco or None,
        ativo=True,
    )

    try:

        db.session.add(empresa)

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        app.logger.exception(
            "Erro de integridade ao cadastrar empresa."
        )

        flash(
            "Não foi possível cadastrar a empresa. "
            "O CNPJ pode já estar cadastrado.",
            "danger"
        )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro inesperado ao cadastrar empresa."
        )

        flash(
            "Ocorreu um erro interno ao cadastrar a empresa. "
            "Verifique os dados e tente novamente.",
            "danger"
        )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

    flash(
        f"Empresa {empresa_nome(empresa)} cadastrada com sucesso.",
        "success"
    )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# ADMIN - DETALHES DA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>"
)
@admin_obrigatorio
def admin_empresa_detalhes(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Usuario.nome.asc()
    ).all()

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.id.desc()
    ).all()

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    return render_template(
        "empresa_detalhes.html",
        empresa=empresa,
        usuarios=usuarios,
        obras=obras,
        total_usuarios=total_usuarios,
        total_obras=total_obras,
        formatar_cnpj=formatar_cnpj,
    )


# ============================================================
# ADMIN - EDITAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def admin_editar_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    titulo = "Editar empresa"

    if request.method == "GET":

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo=titulo
        )

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

    # --------------------------------------------
    # Validação
    # --------------------------------------------

    if not razao_social:

        flash(
            "A Razão Social é obrigatória.",
            "warning"
        )

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo=titulo
        )

    if cnpj and len(cnpj) != 14:

        flash(
            "O CNPJ informado não possui 14 dígitos.",
            "warning"
        )

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo=titulo
        )

    # --------------------------------------------
    # CNPJ duplicado
    # --------------------------------------------

    if cnpj:

        empresa_existente = Empresa.query.filter(
            Empresa.cnpj == cnpj,
            Empresa.id != empresa.id
        ).first()

        if empresa_existente:

            flash(
                "Este CNPJ já pertence a outra empresa.",
                "warning"
            )

            return render_template(
                "empresa_form.html",
                empresa=empresa,
                titulo=titulo
            )

    # --------------------------------------------
    # Atualização
    # --------------------------------------------

    empresa.razao_social = razao_social
    empresa.nome_fantasia = nome_fantasia or None
    empresa.cnpj = cnpj or None
    empresa.telefone = telefone or None
    empresa.email = email or None
    empresa.endereco = endereco or None

    # Checkbox da tela
    empresa.ativo = (
        request.form.get("ativo") == "on"
    )

    try:

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        app.logger.exception(
            "Erro de integridade ao editar empresa."
        )

        flash(
            "Não foi possível salvar as alterações. "
            "Verifique se o CNPJ já está sendo usado.",
            "danger"
        )

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo=titulo
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro inesperado ao editar empresa."
        )

        flash(
            "Ocorreu um erro interno ao salvar a empresa.",
            "danger"
        )

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo=titulo
        )

    flash(
        "Empresa atualizada com sucesso.",
        "success"
    )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# ADMIN - ATIVAR / DESATIVAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/alternar-status",
    methods=["POST"]
)
@admin_obrigatorio
def admin_alternar_status_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa.ativo = not empresa.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro ao alterar status da empresa."
        )

        flash(
            "Não foi possível alterar o status da empresa.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if empresa.ativo:

        flash(
            f"Empresa {empresa_nome(empresa)} ativada.",
            "success"
        )

    else:

        flash(
            f"Empresa {empresa_nome(empresa)} desativada.",
            "warning"
        )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# ADMIN - EXCLUIR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/excluir",
    methods=["POST"]
)
@admin_obrigatorio
def admin_excluir_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    # --------------------------------------------
    # Verifica usuários vinculados
    # --------------------------------------------

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    # --------------------------------------------
    # Verifica obras vinculadas
    # --------------------------------------------

    total_obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    # --------------------------------------------
    # Verifica solicitações vinculadas
    # --------------------------------------------

    total_solicitacoes = (
        Solicitacao.query
        .join(
            Obra,
            Solicitacao.obra_id == Obra.id
        )
        .filter(
            Obra.empresa_id == empresa.id
        )
        .count()
    )

    # --------------------------------------------
    # NÃO apagar dados relacionados
    # --------------------------------------------

    if (
        total_usuarios > 0
        or total_obras > 0
        or total_solicitacoes > 0
    ):

        partes = []

        if total_usuarios:
            partes.append(
                f"{total_usuarios} usuário(s)"
            )

        if total_obras:
            partes.append(
                f"{total_obras} obra(s)"
            )

        if total_solicitacoes:
            partes.append(
                f"{total_solicitacoes} solicitação(ões)"
            )

        detalhes = ", ".join(partes)

        flash(
            "A empresa não pode ser excluída porque possui "
            f"dados vinculados: {detalhes}. "
            "Para preservar os dados, desative a empresa em vez de excluí-la.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    nome_empresa = empresa_nome(empresa)

    try:

        db.session.delete(empresa)

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        app.logger.exception(
            "Erro de integridade ao excluir empresa."
        )

        flash(
            "Não foi possível excluir esta empresa porque existem "
            "dados relacionados a ela.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro inesperado ao excluir empresa."
        )

        flash(
            "Ocorreu um erro interno ao excluir a empresa.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    flash(
        f"Empresa {nome_empresa} excluída com sucesso.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ADMIN - NOVO USUÁRIO DA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/usuarios/novo",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def admin_novo_usuario_empresa(empresa_id):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "GET":

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    nome = (
        request.form.get("nome") or ""
    ).strip()

    usuario = (
        request.form.get("usuario") or ""
    ).strip().lower()

    senha = (
        request.form.get("senha") or ""
    )

    confirmacao = (
        request.form.get("confirmacao")
        or request.form.get("confirmar_senha")
        or ""
    )

    # --------------------------------------------
    # Validações
    # --------------------------------------------

    if not nome:

        flash(
            "Informe o nome do usuário.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    if not usuario:

        flash(
            "Informe o nome de usuário.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    if not senha:

        flash(
            "Informe uma senha.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    if len(senha) < 6:

        flash(
            "A senha deve possuir pelo menos 6 caracteres.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    if senha != confirmacao:

        flash(
            "As senhas não conferem.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    # --------------------------------------------
    # Usuário duplicado
    # --------------------------------------------

    usuario_existente = Usuario.query.filter_by(
        usuario=usuario
    ).first()

    if usuario_existente:

        flash(
            "Este nome de usuário já está sendo utilizado.",
            "warning"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    # --------------------------------------------
    # Criação
    # --------------------------------------------

    novo_usuario = Usuario(
        nome=nome,
        usuario=usuario,
        funcao="administrador_empresa",
        ativo=True,
        empresa_id=empresa.id
    )

    novo_usuario.definir_senha(
        senha
    )

    try:

        db.session.add(novo_usuario)

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        app.logger.exception(
            "Erro de integridade ao criar usuário da empresa."
        )

        flash(
            "Não foi possível criar o usuário. "
            "O nome de usuário pode já existir.",
            "danger"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro inesperado ao criar usuário da empresa."
        )

        flash(
            "Ocorreu um erro interno ao criar o usuário.",
            "danger"
        )

        return render_template(
            "usuario_empresa_form.html",
            empresa=empresa
        )

    flash(
        f"Usuário {nome} criado com sucesso.",
        "success"
    )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# ADMIN - ATIVAR / DESATIVAR USUÁRIO
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/usuarios/<int:usuario_id>/alternar-status",
    methods=["POST"]
)
@admin_obrigatorio
def admin_alternar_status_usuario_empresa(
    empresa_id,
    usuario_id
):

    empresa = db.session.get(
        Empresa,
        empresa_id
    )

    usuario = db.session.get(
        Usuario,
        usuario_id
    )

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if not usuario:

        flash(
            "Usuário não encontrado.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if usuario.empresa_id != empresa.id:

        flash(
            "Este usuário não pertence à empresa selecionada.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    usuario.ativo = not usuario.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro ao alterar status do usuário."
        )

        flash(
            "Não foi possível alterar o status do usuário.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if usuario.ativo:

        flash(
            f"Usuário {usuario.nome} ativado.",
            "success"
        )

    else:

        flash(
            f"Usuário {usuario.nome} desativado.",
            "warning"
        )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
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

    empresa = empresa_usuario_atual()

    if not empresa:

        logout_user()

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    obras_ativas = Obra.query.filter(
        Obra.empresa_id == empresa.id,
        Obra.status.in_([
            "planejamento",
            "em_andamento",
            "em andamento",
            "ativa",
            "ativo"
        ])
    ).count()

    total_obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    return render_template(
        "dashboard.html",
        empresa=empresa,
        obras_ativas=obras_ativas,
        total_obras=total_obras,
        total_usuarios=total_usuarios,
    )


# ============================================================
# OBRAS
# ============================================================

@app.route("/obras")
@login_obrigatorio
def obras():

    if eh_administrador():

        lista_obras = Obra.query.order_by(
            Obra.id.desc()
        ).all()

    else:

        empresa = empresa_usuario_atual()

        lista_obras = Obra.query.filter_by(
            empresa_id=empresa.id
        ).order_by(
            Obra.id.desc()
        ).all()

    return render_template(
        "obras.html",
        obras=lista_obras
    )


# ============================================================
# NOVA OBRA
# ============================================================

@app.route(
    "/obras/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def nova_obra():

    if eh_administrador():

        flash(
            "Selecione uma empresa para trabalhar antes de cadastrar uma obra.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa = empresa_usuario_atual()

    if request.method == "POST":

        nome = (
            request.form.get("nome") or ""
        ).strip()

        cliente = (
            request.form.get("cliente") or ""
        ).strip()

        endereco = (
            request.form.get("endereco") or ""
        ).strip()

        responsavel = (
            request.form.get("responsavel") or ""
        ).strip()

        data_inicio_texto = (
            request.form.get("data_inicio") or ""
        )

        previsao_texto = (
            request.form.get("previsao_termino") or ""
        )

        status = (
            request.form.get("status")
            or "planejamento"
        ).strip()

        observacoes = (
            request.form.get("observacoes") or ""
        ).strip()

        if not nome:

            flash(
                "Informe o nome da obra.",
                "warning"
            )

            return render_template(
                "obra_form.html",
                obra=None
            )

        data_inicio = None
        previsao_termino = None

        try:

            if data_inicio_texto:
                data_inicio = datetime.strptime(
                    data_inicio_texto,
                    "%Y-%m-%d"
                ).date()

            if previsao_texto:
                previsao_termino = datetime.strptime(
                    previsao_texto,
                    "%Y-%m-%d"
                ).date()

        except ValueError:

            flash(
                "Informe datas válidas.",
                "warning"
            )

            return render_template(
                "obra_form.html",
                obra=None
            )

        obra = Obra(
            empresa_id=empresa.id,
            nome=nome,
            cliente=cliente or None,
            endereco=endereco or None,
            responsavel=responsavel or None,
            data_inicio=data_inicio,
            previsao_termino=previsao_termino,
            status=status,
            observacoes=observacoes or None
        )

        try:

            db.session.add(obra)
            db.session.commit()

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao cadastrar obra."
            )

            flash(
                "Não foi possível cadastrar a obra.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=None
            )

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

    lista_materiais = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    return render_template(
        "materiais.html",
        materiais=lista_materiais
    )


# ============================================================
# NOVO MATERIAL
# ============================================================

@app.route(
    "/materiais/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def novo_material():

    if request.method == "POST":

        categoria = (
            request.form.get("categoria") or ""
        ).strip()

        nome = (
            request.form.get("nome") or ""
        ).strip()

        descricao = (
            request.form.get("descricao") or ""
        ).strip()

        unidade = (
            request.form.get("unidade") or ""
        ).strip()

        estoque_minimo_texto = (
            request.form.get("estoque_minimo")
            or "0"
        )

        if not categoria or not nome or not unidade:

            flash(
                "Categoria, nome e unidade são obrigatórios.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        try:

            estoque_minimo = float(
                estoque_minimo_texto
            )

            if estoque_minimo < 0:
                raise ValueError

        except ValueError:

            flash(
                "O estoque mínimo informado é inválido.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        material = Material(
            categoria=categoria,
            nome=nome,
            descricao=descricao or None,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=0,
            ativo=True
        )

        try:

            db.session.add(material)
            db.session.commit()

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao cadastrar material."
            )

            flash(
                "Não foi possível cadastrar o material.",
                "danger"
            )

            return render_template(
                "material_form.html"
            )

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

    if eh_administrador():

        lista_solicitacoes = Solicitacao.query.order_by(
            Solicitacao.id.desc()
        ).all()

    else:

        empresa = empresa_usuario_atual()

        lista_solicitacoes = (
            Solicitacao.query
            .join(
                Obra,
                Solicitacao.obra_id == Obra.id
            )
            .filter(
                Obra.empresa_id == empresa.id
            )
            .order_by(
                Solicitacao.id.desc()
            )
            .all()
        )

    return render_template(
        "solicitacoes.html",
        solicitacoes=lista_solicitacoes
    )


# ============================================================
# NOVA SOLICITAÇÃO
# ============================================================

@app.route(
    "/solicitacoes/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def nova_solicitacao():

    if eh_administrador():

        flash(
            "O administrador global deve estar vinculado a uma empresa para criar solicitações.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa = empresa_usuario_atual()

    obras_empresa = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.nome.asc()
    ).all()

    materiais_disponiveis = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    if request.method == "POST":

        obra_id_texto = (
            request.form.get("obra_id") or ""
        )

        material_id_texto = (
            request.form.get("material_id") or ""
        )

        quantidade_texto = (
            request.form.get("quantidade") or ""
        )

        observacao = (
            request.form.get("observacao") or ""
        ).strip()

        try:

            obra_id = int(
                obra_id_texto
            )

            material_id = int(
                material_id_texto
            )

            quantidade = float(
                quantidade_texto
            )

        except (ValueError, TypeError):

            flash(
                "Informe obra, material e quantidade válidos.",
                "warning"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_empresa,
                materiais=materiais_disponiveis
            )

        if quantidade <= 0:

            flash(
                "A quantidade deve ser maior que zero.",
                "warning"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_empresa,
                materiais=materiais_disponiveis
            )

        obra = Obra.query.filter_by(
            id=obra_id,
            empresa_id=empresa.id
        ).first()

        material = db.session.get(
            Material,
            material_id
        )

        if not obra:

            flash(
                "A obra selecionada não pertence à sua empresa.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_empresa,
                materiais=materiais_disponiveis
            )

        if not material or not material.ativo:

            flash(
                "Material selecionado não encontrado ou inativo.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_empresa,
                materiais=materiais_disponiveis
            )

        solicitacao = Solicitacao(
            obra_id=obra.id,
            material_id=material.id,
            usuario_id=current_user.id,
            quantidade=quantidade,
            observacao=observacao or None,
            status="pendente"
        )

        try:

            db.session.add(solicitacao)
            db.session.commit()

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao cadastrar solicitação."
            )

            flash(
                "Não foi possível registrar a solicitação.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_empresa,
                materiais=materiais_disponiveis
            )

        flash(
            "Solicitação registrada com sucesso.",
            "success"
        )

        return redirect(
            url_for("solicitacoes")
        )

    return render_template(
        "solicitacao_form.html",
        obras=obras_empresa,
        materiais=materiais_disponiveis
    )


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    app.logger.warning(
        "Página não encontrada: %s",
        request.path
    )

    if request.accept_mimetypes.accept_html:

        try:

            return render_template(
                "base.html",
                error_code=404,
                error_title="Página não encontrada",
                error_message=(
                    "A página que você tentou acessar não existe "
                    "ou foi removida."
                )
            ), 404

        except Exception:

            return make_response(
                """
                <!doctype html>
                <html lang="pt-BR">
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport"
                          content="width=device-width,initial-scale=1">
                    <title>404 - Página não encontrada</title>
                </head>
                <body style="
                    font-family:Arial,sans-serif;
                    padding:40px;
                    background:#f5f6f8;
                ">
                    <h1>404 - Página não encontrada</h1>
                    <p>A página solicitada não existe.</p>
                </body>
                </html>
                """,
                404
            )

    return "404 - Página não encontrada", 404


@app.errorhandler(500)
def erro_servidor(error):

    db.session.rollback()

    app.logger.exception(
        "Erro interno do servidor."
    )

    try:

        return render_template(
            "base.html",
            error_code=500,
            error_title="Erro interno do servidor",
            error_message=(
                "O sistema encontrou um problema ao processar "
                "esta solicitação. Tente novamente."
            )
        ), 500

    except Exception:

        return make_response(
            """
            <!doctype html>
            <html lang="pt-BR">
            <head>
                <meta charset="utf-8">
                <meta name="viewport"
                      content="width=device-width,initial-scale=1">
                <title>500 - Erro interno</title>
            </head>
            <body style="
                font-family:Arial,sans-serif;
                padding:40px;
                background:#f5f6f8;
            ">
                <h1>500 - Erro interno do servidor</h1>
                <p>
                    O sistema encontrou um erro inesperado.
                    Consulte os logs do servidor.
                </p>
            </body>
            </html>
            """,
            500
        )


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    with app.app_context():

        db.create_all()

        # --------------------------------------------
        # Cria empresa padrão somente se não existir
        # nenhuma empresa
        # --------------------------------------------

        if Empresa.query.count() == 0:

            empresa_padrao = Empresa(
                razao_social="Construtora Pro",
                nome_fantasia="Construtora Pro",
                ativo=True
            )

            db.session.add(
                empresa_padrao
            )

            db.session.commit()

        # --------------------------------------------
        # Configuração do administrador global
        # --------------------------------------------

        admin_user = (
            os.getenv("ADMIN_USER")
            or "admin"
        ).strip().lower()

        admin_password = (
            os.getenv("ADMIN_PASSWORD")
            or ""
        )

        admin = Usuario.query.filter_by(
            usuario=admin_user
        ).first()

        if admin:

            # Garante que o usuário configurado
            # no Render continue sendo ADM global
            admin.funcao = "ADM"
            admin.empresa_id = None
            admin.ativo = True

            db.session.commit()

        elif admin_password:

            novo_admin = Usuario(
                nome="Administrador",
                usuario=admin_user,
                funcao="ADM",
                ativo=True,
                empresa_id=None
            )

            novo_admin.definir_senha(
                admin_password
            )

            db.session.add(
                novo_admin
            )

            db.session.commit()


# ============================================================
# STARTUP
# ============================================================

inicializar_banco()


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=False
    )
