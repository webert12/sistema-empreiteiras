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
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///construtora_pro.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta página."
login_manager.login_message_category = "warning"

logging.basicConfig(level=logging.INFO)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_cnpj(valor):
    """
    Mantém somente números do CNPJ.
    """
    return "".join(
        caractere
        for caractere in (valor or "")
        if caractere.isdigit()
    )


def normalizar_usuario(valor):
    """
    Normaliza o nome de usuário.
    """
    return (valor or "").strip().lower()


def usuario_atual():
    if not current_user.is_authenticated:
        return None

    return current_user


def eh_administrador():
    """
    ADM global do sistema.
    """
    if not current_user.is_authenticated:
        return False

    return str(
        getattr(current_user, "funcao", "")
    ).lower() == "adm"


def eh_administrador_empresa():
    """
    Administrador vinculado a uma empresa.
    """
    if not current_user.is_authenticated:
        return False

    funcao = str(
        getattr(current_user, "funcao", "")
    ).lower()

    return funcao in (
        "administrador_empresa",
        "admin_empresa",
    )


def empresa_usuario_atual():
    """
    Retorna a empresa vinculada ao usuário logado.
    O ADM global não possui empresa.
    """
    if not current_user.is_authenticated:
        return None

    empresa_id = getattr(
        current_user,
        "empresa_id",
        None
    )

    if not empresa_id:
        return None

    return db.session.get(
        Empresa,
        empresa_id
    )


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
        db.String(255),
        nullable=False
    )

    nome_fantasia = db.Column(
        db.String(255),
        nullable=True
    )

    cnpj = db.Column(
        db.String(20),
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

    def __repr__(self):
        return f"<Empresa {self.nome_fantasia or self.razao_social}>"


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

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
        db.ForeignKey("empresas.id"),
        nullable=True
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(
            senha
        )

    def verificar_senha(self, senha):
        if not self.senha_hash:
            return False

        return check_password_hash(
            self.senha_hash,
            senha
        )

    def __repr__(self):
        return f"<Usuario {self.usuario}>"


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
        default=datetime.utcnow,
        nullable=False
    )

    solicitacoes = db.relationship(
        "Solicitacao",
        backref="obra",
        lazy=True
    )

    def __repr__(self):
        return f"<Obra {self.nome}>"


class Material(db.Model):
    __tablename__ = "materiais"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    categoria = db.Column(
        db.String(150),
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
        default=0,
        nullable=False
    )

    estoque_atual = db.Column(
        db.Float,
        default=0,
        nullable=False
    )

    ativo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    solicitacoes = db.relationship(
        "Solicitacao",
        backref="material",
        lazy=True
    )

    def __repr__(self):
        return f"<Material {self.nome}>"


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
        db.String(50),
        default="pendente",
        nullable=False
    )

    criado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    usuario = db.relationship(
        "Usuario",
        backref="solicitacoes",
        lazy=True
    )

    def __repr__(self):
        return f"<Solicitacao {self.id}>"


# ============================================================
# LOGIN MANAGER
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


# ============================================================
# DECORATORS
# ============================================================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:

            flash(
                "Faça login para acessar esta página.",
                "warning"
            )

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        if not current_user.ativo:

            logout_user()

            flash(
                "Seu usuário está desativado.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # ADM global não precisa de empresa.
        if eh_administrador():
            return funcao(*args, **kwargs)

        empresa = empresa_usuario_atual()

        if not empresa:

            logout_user()

            flash(
                "A empresa vinculada a este usuário não existe.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        if not empresa.ativo:

            logout_user()

            flash(
                "A empresa vinculada a este usuário está inativa.",
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
# CONTEXT PROCESSOR
# ============================================================

@app.context_processor
def contexto_global():

    empresa = None

    if current_user.is_authenticated:

        if not eh_administrador():

            empresa = empresa_usuario_atual()

    return {
        "usuario_logado": usuario_atual(),
        "usuario_eh_admin": eh_administrador(),
        "usuario_eh_admin_empresa": eh_administrador_empresa(),
        "empresa_usuario_logado": empresa,
    }


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    # Se já estiver autenticado,
    # não precisa voltar para a tela de login.
    if current_user.is_authenticated:

        if eh_administrador():

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = request.form.get(
            "senha"
        ) or ""

        if not usuario_login or not senha:

            flash(
                "Informe usuário e senha.",
                "warning"
            )

            return render_template(
                "login.html"
            )

        # ====================================================
        # BUSCA ROBUSTA DO USUÁRIO
        # ====================================================
        # Usa lower() no banco para aceitar também usuários
        # antigos que eventualmente tenham sido cadastrados
        # com letras maiúsculas.
        # ====================================================

        usuario = Usuario.query.filter(
            db.func.lower(
                Usuario.usuario
            ) == usuario_login
        ).first()

        if not usuario:

            flash(
                "Usuário ou senha inválidos.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        # ====================================================
        # SENHA
        # ====================================================

        if not usuario.verificar_senha(senha):

            flash(
                "Usuário ou senha inválidos.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        # ====================================================
        # USUÁRIO ATIVO
        # ====================================================

        if not usuario.ativo:

            flash(
                "Este usuário está desativado.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        # ====================================================
        # ADM GLOBAL
        # ====================================================
        # O ADM global não possui empresa_id.
        # Ele entra normalmente.
        # ====================================================

        if str(
            usuario.funcao
        ).lower() == "adm":

            login_user(
                usuario,
                remember=True
            )

            proxima = request.args.get(
                "next"
            )

            if (
                proxima
                and proxima.startswith("/")
                and not proxima.startswith("//")
            ):
                return redirect(proxima)

            return redirect(
                url_for("admin_dashboard")
            )

        # ====================================================
        # USUÁRIO DE EMPRESA
        # ====================================================
        # CORREÇÃO PRINCIPAL:
        #
        # NÃO usamos current_user aqui.
        #
        # O usuário ainda não foi autenticado.
        # Portanto usamos diretamente usuario.empresa_id.
        # ====================================================

        if not usuario.empresa_id:

            flash(
                "Este usuário não está vinculado a nenhuma empresa.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        empresa = db.session.get(
            Empresa,
            usuario.empresa_id
        )

        if not empresa:

            flash(
                "A empresa vinculada a este usuário não existe.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if not empresa.ativo:

            flash(
                "A empresa vinculada a este usuário está inativa.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        # ====================================================
        # AGORA EFETUA O LOGIN
        # ====================================================

        login_user(
            usuario,
            remember=True
        )

        proxima = request.args.get(
            "next"
        )

        if (
            proxima
            and proxima.startswith("/")
            and not proxima.startswith("//")
        ):
            return redirect(proxima)

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    logout_user()

    flash(
        "Sessão encerrada com sucesso.",
        "success"
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
        Empresa.razao_social.asc()
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

    if request.method == "POST":

        razao_social = (
            request.form.get("razao_social")
            or ""
        ).strip()

        nome_fantasia = (
            request.form.get("nome_fantasia")
            or ""
        ).strip()

        cnpj = normalizar_cnpj(
            request.form.get("cnpj")
        )

        telefone = (
            request.form.get("telefone")
            or ""
        ).strip()

        email = (
            request.form.get("email")
            or ""
        ).strip()

        endereco = (
            request.form.get("endereco")
            or ""
        ).strip()

        if not razao_social:

            flash(
                "Informe a razão social da empresa.",
                "warning"
            )

            return render_template(
                "empresa_form.html",
                empresa=None,
                titulo=titulo
            )

        if cnpj:

            empresa_existente = Empresa.query.filter_by(
                cnpj=cnpj
            ).first()

            if empresa_existente:

                flash(
                    "Já existe uma empresa cadastrada com este CNPJ.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    empresa=None,
                    titulo=titulo
                )

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

            flash(
                "Empresa cadastrada com sucesso.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_empresa_detalhes",
                    empresa_id=empresa.id
                )
            )

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível cadastrar a empresa. "
                "Verifique se o CNPJ já está cadastrado.",
                "danger"
            )

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao cadastrar empresa."
            )

            flash(
                "Ocorreu um erro ao cadastrar a empresa.",
                "danger"
            )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo=titulo
        )

    return render_template(
        "empresa_form.html",
        empresa=None,
        titulo=titulo
    )


# ============================================================
# ADMIN - DETALHES DA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>"
)
@admin_obrigatorio
def admin_empresa_detalhes(
    empresa_id
):

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
        Obra.nome.asc()
    ).all()

    return render_template(
        "empresa_detalhes.html",
        empresa=empresa,
        usuarios=usuarios,
        obras=obras,
    )


# ============================================================
# ADMIN - EDITAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def admin_editar_empresa(
    empresa_id
):

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

    if request.method == "POST":

        razao_social = (
            request.form.get("razao_social")
            or ""
        ).strip()

        nome_fantasia = (
            request.form.get("nome_fantasia")
            or ""
        ).strip()

        cnpj = normalizar_cnpj(
            request.form.get("cnpj")
        )

        telefone = (
            request.form.get("telefone")
            or ""
        ).strip()

        email = (
            request.form.get("email")
            or ""
        ).strip()

        endereco = (
            request.form.get("endereco")
            or ""
        ).strip()

        if not razao_social:

            flash(
                "Informe a razão social da empresa.",
                "warning"
            )

            return render_template(
                "empresa_form.html",
                empresa=empresa,
                titulo=titulo
            )

        if cnpj:

            empresa_existente = Empresa.query.filter(
                Empresa.cnpj == cnpj,
                Empresa.id != empresa.id
            ).first()

            if empresa_existente:

                flash(
                    "Já existe outra empresa cadastrada com este CNPJ.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    empresa=empresa,
                    titulo=titulo
                )

        empresa.razao_social = razao_social

        empresa.nome_fantasia = (
            nome_fantasia or None
        )

        empresa.cnpj = (
            cnpj or None
        )

        empresa.telefone = (
            telefone or None
        )

        empresa.email = (
            email or None
        )

        empresa.endereco = (
            endereco or None
        )

        # Checkbox da empresa
        empresa.ativo = (
            request.form.get("ativo")
            == "on"
        )

        try:

            db.session.commit()

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

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível atualizar a empresa. "
                "Verifique o CNPJ.",
                "danger"
            )

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao editar empresa."
            )

            flash(
                "Ocorreu um erro ao atualizar a empresa.",
                "danger"
            )

    return render_template(
        "empresa_form.html",
        empresa=empresa,
        titulo=titulo
    )


# ============================================================
# ADMIN - ATIVAR / DESATIVAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/alternar-status",
    methods=["POST"]
)
@admin_obrigatorio
def admin_alternar_status_empresa(
    empresa_id
):

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

        if empresa.ativo:

            flash(
                "Empresa ativada com sucesso.",
                "success"
            )

        else:

            flash(
                "Empresa desativada com sucesso.",
                "warning"
            )

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


# ============================================================
# ADMIN - EXCLUIR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/excluir",
    methods=["POST"]
)
@admin_obrigatorio
def admin_excluir_empresa(
    empresa_id
):

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

    # ========================================================
    # PROTEÇÃO CONTRA EXCLUSÃO DE DADOS
    # ========================================================

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_solicitacoes = (
        Solicitacao.query
        .join(Obra, Solicitacao.obra_id == Obra.id)
        .filter(Obra.empresa_id == empresa.id)
        .count()
    )

    if (
        total_usuarios > 0
        or total_obras > 0
        or total_solicitacoes > 0
    ):

        flash(
            "Esta empresa possui dados vinculados "
            "(usuários, obras ou solicitações) e não pode "
            "ser excluída. Desative a empresa para impedir "
            "seu uso sem apagar os dados.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    nome_empresa = (
        empresa.nome_fantasia
        or empresa.razao_social
    )

    try:

        db.session.delete(
            empresa
        )

        db.session.commit()

        flash(
            f'A empresa "{nome_empresa}" foi excluída com sucesso.',
            "success"
        )

    except Exception:

        db.session.rollback()

        app.logger.exception(
            "Erro ao excluir empresa."
        )

        flash(
            "Não foi possível excluir a empresa.",
            "danger"
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
def admin_novo_usuario_empresa(
    empresa_id
):

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

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        usuario_login = normalizar_usuario(
            request.form.get("usuario")
        )

        senha = (
            request.form.get("senha")
            or ""
        )

        confirmacao = (
            request.form.get("confirmacao")
            or request.form.get("confirmar_senha")
            or ""
        )

        funcao = (
            request.form.get("funcao")
            or "funcionario"
        ).strip().lower()

        # ====================================================
        # VALIDAÇÕES
        # ====================================================

        if not nome:

            flash(
                "Informe o nome do usuário.",
                "warning"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        if not usuario_login:

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

        if senha != confirmacao:

            flash(
                "As senhas não coincidem.",
                "danger"
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

        # ====================================================
        # NÃO PERMITIR CRIAÇÃO DE ADM GLOBAL POR ESTA TELA
        # ====================================================

        if funcao == "adm":

            funcao = "administrador_empresa"

        usuarios_existente = Usuario.query.filter(
            db.func.lower(
                Usuario.usuario
            ) == usuario_login
        ).first()

        if usuarios_existente:

            flash(
                "Este nome de usuário já está cadastrado.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        usuario = Usuario(
            nome=nome,
            usuario=usuario_login,
            funcao=funcao,
            ativo=True,
            empresa_id=empresa.id,
        )

        usuario.definir_senha(
            senha
        )

        try:

            db.session.add(
                usuario
            )

            db.session.commit()

            flash(
                "Usuário cadastrado com sucesso.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_empresa_detalhes",
                    empresa_id=empresa.id
                )
            )

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível cadastrar o usuário. "
                "O nome de usuário pode já estar em uso.",
                "danger"
            )

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao cadastrar usuário da empresa."
            )

            flash(
                "Ocorreu um erro ao cadastrar o usuário.",
                "danger"
            )

    return render_template(
        "usuario_empresa_form.html",
        empresa=empresa
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

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    usuario = Usuario.query.filter_by(
        id=usuario_id,
        empresa_id=empresa.id
    ).first()

    if not usuario:

        flash(
            "Usuário não encontrado nesta empresa.",
            "warning"
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

        if usuario.ativo:

            flash(
                "Usuário ativado com sucesso.",
                "success"
            )

        else:

            flash(
                "Usuário desativado com sucesso.",
                "warning"
            )

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


# ============================================================
# DASHBOARD DA EMPRESA
# ============================================================

@app.route("/")
@login_obrigatorio
def dashboard():

    # ADM global utiliza seu próprio dashboard.
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

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).all()

    obras_ativas = [
        obra
        for obra in obras
        if str(
            obra.status or ""
        ).lower()
        not in (
            "concluida",
            "concluído",
            "concluída",
            "cancelada",
            "cancelado",
        )
    ]

    total_obras = len(obras)

    total_obras_ativas = len(
        obras_ativas
    )

    total_solicitacoes = (
        Solicitacao.query
        .join(Obra, Solicitacao.obra_id == Obra.id)
        .filter(
            Obra.empresa_id == empresa.id
        )
        .count()
    )

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    solicitacoes_pendentes = (
        Solicitacao.query
        .join(Obra, Solicitacao.obra_id == Obra.id)
        .filter(
            Obra.empresa_id == empresa.id,
            Solicitacao.status == "pendente"
        )
        .count()
    )

    return render_template(
        "dashboard.html",
        empresa=empresa,
        obras=obras,
        obras_ativas=obras_ativas,
        total_obras=total_obras,
        total_obras_ativas=total_obras_ativas,
        total_solicitacoes=total_solicitacoes,
        solicitacoes_pendentes=solicitacoes_pendentes,
        total_usuarios=total_usuarios,
    )


# ============================================================
# OBRAS
# ============================================================

@app.route("/obras")
@login_obrigatorio
def obras():

    if eh_administrador():

        obras_lista = Obra.query.order_by(
            Obra.criado_em.desc()
        ).all()

    else:

        empresa = empresa_usuario_atual()

        if not empresa:

            return redirect(
                url_for("login")
            )

        obras_lista = Obra.query.filter_by(
            empresa_id=empresa.id
        ).order_by(
            Obra.criado_em.desc()
        ).all()

    return render_template(
        "obras.html",
        obras=obras_lista
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

    if not empresa:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        cliente = (
            request.form.get("cliente")
            or ""
        ).strip()

        endereco = (
            request.form.get("endereco")
            or ""
        ).strip()

        responsavel = (
            request.form.get("responsavel")
            or ""
        ).strip()

        data_inicio_str = (
            request.form.get("data_inicio")
            or ""
        ).strip()

        previsao_termino_str = (
            request.form.get("previsao_termino")
            or ""
        ).strip()

        status = (
            request.form.get("status")
            or "planejamento"
        ).strip().lower()

        observacoes = (
            request.form.get("observacoes")
            or ""
        ).strip()

        if not nome:

            flash(
                "Informe o nome da obra.",
                "warning"
            )

            return render_template(
                "obra_form.html",
                obra=None,
                empresa=empresa
            )

        data_inicio = None
        previsao_termino = None

        try:

            if data_inicio_str:

                data_inicio = datetime.strptime(
                    data_inicio_str,
                    "%Y-%m-%d"
                ).date()

            if previsao_termino_str:

                previsao_termino = datetime.strptime(
                    previsao_termino_str,
                    "%Y-%m-%d"
                ).date()

        except ValueError:

            flash(
                "Informe datas válidas.",
                "danger"
            )

            return render_template(
                "obra_form.html",
                obra=None,
                empresa=empresa
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
            observacoes=observacoes or None,
        )

        try:

            db.session.add(
                obra
            )

            db.session.commit()

            flash(
                "Obra cadastrada com sucesso.",
                "success"
            )

            return redirect(
                url_for("obras")
            )

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
        obra=None,
        empresa=empresa
    )


# ============================================================
# MATERIAIS
# ============================================================

@app.route("/materiais")
@login_obrigatorio
def materiais():

    materiais_lista = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.categoria.asc(),
        Material.nome.asc()
    ).all()

    return render_template(
        "materiais.html",
        materiais=materiais_lista
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
            or ""
        ).strip()

        estoque_minimo_str = (
            request.form.get("estoque_minimo")
            or "0"
        )

        estoque_atual_str = (
            request.form.get("estoque_atual")
            or "0"
        )

        if not categoria or not nome or not unidade:

            flash(
                "Preencha categoria, nome e unidade.",
                "warning"
            )

            return render_template(
                "material_form.html",
                material=None
            )

        try:

            estoque_minimo = float(
                estoque_minimo_str
            )

            estoque_atual = float(
                estoque_atual_str
            )

        except ValueError:

            flash(
                "Os valores de estoque devem ser numéricos.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=None
            )

        material = Material(
            categoria=categoria,
            nome=nome,
            descricao=descricao or None,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual,
            ativo=True,
        )

        try:

            db.session.add(
                material
            )

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

            app.logger.exception(
                "Erro ao cadastrar material."
            )

            flash(
                "Não foi possível cadastrar o material.",
                "danger"
            )

    return render_template(
        "material_form.html",
        material=None
    )


# ============================================================
# SOLICITAÇÕES
# ============================================================

@app.route("/solicitacoes")
@login_obrigatorio
def solicitacoes():

    if eh_administrador():

        solicitacoes_lista = (
            Solicitacao.query
            .order_by(
                Solicitacao.criado_em.desc()
            )
            .all()
        )

    else:

        empresa = empresa_usuario_atual()

        if not empresa:

            return redirect(
                url_for("login")
            )

        solicitacoes_lista = (
            Solicitacao.query
            .join(
                Obra,
                Solicitacao.obra_id == Obra.id
            )
            .filter(
                Obra.empresa_id == empresa.id
            )
            .order_by(
                Solicitacao.criado_em.desc()
            )
            .all()
        )

    return render_template(
        "solicitacoes.html",
        solicitacoes=solicitacoes_lista
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
            "O ADM global não pode criar solicitações sem selecionar uma empresa.",
            "warning"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa = empresa_usuario_atual()

    if not empresa:

        return redirect(
            url_for("login")
        )

    obras_lista = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.nome.asc()
    ).all()

    materiais_lista = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.nome.asc()
    ).all()

    if request.method == "POST":

        obra_id_str = (
            request.form.get("obra_id")
            or ""
        )

        material_id_str = (
            request.form.get("material_id")
            or ""
        )

        quantidade_str = (
            request.form.get("quantidade")
            or ""
        )

        observacao = (
            request.form.get("observacao")
            or ""
        ).strip()

        try:

            obra_id = int(
                obra_id_str
            )

            material_id = int(
                material_id_str
            )

            quantidade = float(
                quantidade_str
            )

        except (ValueError, TypeError):

            flash(
                "Informe obra, material e quantidade válidos.",
                "warning"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_lista,
                materiais=materiais_lista
            )

        if quantidade <= 0:

            flash(
                "A quantidade deve ser maior que zero.",
                "warning"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_lista,
                materiais=materiais_lista
            )

        obra = Obra.query.filter_by(
            id=obra_id,
            empresa_id=empresa.id
        ).first()

        if not obra:

            flash(
                "A obra selecionada não pertence à empresa.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_lista,
                materiais=materiais_lista
            )

        material = Material.query.filter_by(
            id=material_id,
            ativo=True
        ).first()

        if not material:

            flash(
                "Material não encontrado ou inativo.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_lista,
                materiais=materiais_lista
            )

        solicitacao = Solicitacao(
            obra_id=obra.id,
            material_id=material.id,
            usuario_id=current_user.id,
            quantidade=quantidade,
            observacao=observacao or None,
            status="pendente",
        )

        try:

            db.session.add(
                solicitacao
            )

            db.session.commit()

            flash(
                "Solicitação criada com sucesso.",
                "success"
            )

            return redirect(
                url_for("solicitacoes")
            )

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "Erro ao criar solicitação."
            )

            flash(
                "Não foi possível criar a solicitação.",
                "danger"
            )

    return render_template(
        "solicitacao_form.html",
        obras=obras_lista,
        materiais=materiais_lista
    )


# ============================================================
# ERRO 404
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    return render_template(
        "base.html",
        error_code=404,
        error_title="Página não encontrada",
        error_message=(
            "A página que você tentou acessar "
            "não existe ou foi removida."
        )
    ), 404


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_servidor(error):

    db.session.rollback()

    app.logger.exception(
        "Erro interno do servidor."
    )

    return render_template(
        "base.html",
        error_code=500,
        error_title="Erro interno do servidor",
        error_message=(
            "O sistema encontrou um erro inesperado. "
            "Verifique os logs do servidor para identificar "
            "a causa."
        )
    ), 500


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    with app.app_context():

        db.create_all()

        # ----------------------------------------------------
        # EMPRESA PADRÃO
        # ----------------------------------------------------

        empresa_padrao = Empresa.query.first()

        if not empresa_padrao:

            empresa_padrao = Empresa(
                razao_social="Construtora Pro",
                nome_fantasia="Construtora Pro",
                ativo=True,
            )

            db.session.add(
                empresa_padrao
            )

            db.session.commit()

        # ----------------------------------------------------
        # ADM GLOBAL
        # ----------------------------------------------------

        admin_user = normalizar_usuario(
            os.getenv(
                "ADMIN_USER",
                "admin"
            )
        )

        admin_password = os.getenv(
            "ADMIN_PASSWORD"
        )

        usuario_admin = Usuario.query.filter(
            db.func.lower(
                Usuario.usuario
            ) == admin_user
        ).first()

        if usuario_admin:

            usuario_admin.funcao = "ADM"

            usuario_admin.empresa_id = None

            usuario_admin.ativo = True

            # IMPORTANTE:
            # não substitui a senha existente.
            # A senha só é criada automaticamente
            # quando o ADM ainda não existe.

            db.session.commit()

        elif admin_password:

            novo_admin = Usuario(
                nome="Administrador",
                usuario=admin_user,
                funcao="ADM",
                ativo=True,
                empresa_id=None,
            )

            novo_admin.definir_senha(
                admin_password
            )

            db.session.add(
                novo_admin
            )

            try:

                db.session.commit()

            except IntegrityError:

                db.session.rollback()

                app.logger.exception(
                    "Não foi possível criar o ADM inicial."
                )


# ============================================================
# INICIALIZAÇÃO
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
