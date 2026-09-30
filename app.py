import os
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

login_manager.login_message = (
    "Faça login para continuar."
)

login_manager.login_message_category = "warning"


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
        nullable=True
    )

    cnpj = db.Column(
        db.String(30),
        unique=True,
        nullable=True
    )

    telefone = db.Column(
        db.String(30),
        nullable=True
    )

    email = db.Column(
        db.String(150),
        nullable=True
    )

    endereco = db.Column(
        db.String(300),
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
        default=datetime.utcnow
    )

    def definir_senha(self, senha):

        self.senha_hash = generate_password_hash(
            senha
        )

    def verificar_senha(self, senha):

        if not self.senha_hash:
            return False

        try:

            return check_password_hash(
                self.senha_hash,
                senha
            )

        except Exception:

            return False


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
        db.String(200),
        nullable=True
    )

    endereco = db.Column(
        db.String(300),
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

    __tablename__ = "materiais"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    categoria = db.Column(
        db.String(100),
        nullable=False
    )

    nome = db.Column(
        db.String(200),
        nullable=False
    )

    descricao = db.Column(
        db.Text,
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

    except (ValueError, TypeError):

        return None


# ============================================================
# HELPERS
# ============================================================

def usuario_atual():

    if current_user.is_authenticated:
        return current_user

    return None


def eh_administrador():

    usuario = usuario_atual()

    if not usuario:
        return False

    return (
        usuario.funcao
        and usuario.funcao.strip().lower() == "adm"
    )


def eh_administrador_empresa():

    usuario = usuario_atual()

    if not usuario:
        return False

    return (
        usuario.funcao
        and usuario.funcao.strip().lower()
        in (
            "administrador_empresa",
            "admin_empresa",
        )
    )


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


def login_obrigatorio(funcao):

    @wraps(funcao)
    def wrapper(*args, **kwargs):

        if not current_user.is_authenticated:

            flash(
                "Faça login para continuar.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        usuario = usuario_atual()

        if not usuario or not usuario.ativo:

            logout_user()
            session.clear()

            flash(
                "Seu usuário está desativado.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        if usuario.empresa_id:

            empresa = empresa_usuario_atual()

            if not empresa or not empresa.ativo:

                logout_user()
                session.clear()

                flash(
                    "Esta empresa está inativa ou não foi encontrada.",
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
                "Acesso permitido somente ao administrador da plataforma.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return funcao(*args, **kwargs)

    return wrapper


# ============================================================
# CONTEXTO GLOBAL
# ============================================================

@app.context_processor
def contexto_global():

    usuario = usuario_atual()

    empresa = None

    if usuario and usuario.empresa_id:

        empresa = empresa_usuario_atual()

    return {
        "usuario_logado": usuario,
        "usuario_eh_admin": eh_administrador(),
        "usuario_eh_admin_empresa": eh_administrador_empresa(),
        "empresa_usuario_logado": empresa,
    }


# ============================================================
# BANCO DE DADOS
# ============================================================

def inicializar_banco():

    with app.app_context():

        try:

            db.create_all()

            empresa_padrao = Empresa.query.first()

            if not empresa_padrao:

                empresa_padrao = Empresa(
                    razao_social="Empresa de Construção",
                    nome_fantasia="Construtora Pro",
                    ativo=True
                )

                db.session.add(
                    empresa_padrao
                )

                db.session.commit()

            admin_usuario = (
                os.getenv(
                    "ADMIN_USER",
                    "admin"
                )
                or "admin"
            ).strip()

            admin_senha = os.getenv(
                "ADMIN_PASSWORD"
            )

            if admin_usuario:

                admin_existente = Usuario.query.filter(
                    db.func.lower(
                        Usuario.usuario
                    ) == admin_usuario.lower()
                ).first()

                if admin_existente:

                    admin_existente.funcao = "ADM"
                    admin_existente.empresa_id = None
                    admin_existente.ativo = True

                    db.session.commit()

                elif admin_senha:

                    novo_admin = Usuario(
                        nome="Administrador da Plataforma",
                        usuario=admin_usuario,
                        funcao="ADM",
                        ativo=True,
                        empresa_id=None
                    )

                    novo_admin.definir_senha(
                        admin_senha
                    )

                    db.session.add(
                        novo_admin
                    )

                    db.session.commit()

        except Exception as erro:

            db.session.rollback()

            print(
                "ERRO AO INICIALIZAR BANCO:",
                repr(erro)
            )


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
            url_for("dashboard")
        )

    if request.method == "POST":

        usuario_digitado = (
            request.form.get("usuario")
            or ""
        ).strip()

        senha = (
            request.form.get("senha")
            or ""
        )

        if not usuario_digitado or not senha:

            flash(
                "Informe usuário e senha.",
                "warning"
            )

            return render_template(
                "login.html"
            )

        usuario = Usuario.query.filter(
            db.func.lower(
                Usuario.usuario
            ) == usuario_digitado.lower()
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
                "Este usuário está desativado.",
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

        if usuario.empresa_id:

            empresa = db.session.get(
                Empresa,
                usuario.empresa_id
            )

            if not empresa:

                flash(
                    "A empresa vinculada ao usuário não foi encontrada.",
                    "danger"
                )

                return render_template(
                    "login.html"
                )

            if not empresa.ativo:

                flash(
                    "Esta empresa está temporariamente inativa.",
                    "danger"
                )

                return render_template(
                    "login.html"
                )

        login_user(usuario)

        session["usuario_id"] = usuario.id

        if eh_administrador():

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    logout_user()

    session.clear()

    flash(
        "Você saiu do sistema.",
        "success"
    )

    return redirect(
        url_for("login")
    )


# ============================================================
# PAINEL ADM
# ============================================================

@app.route("/admin")
@admin_obrigatorio
def admin_dashboard():

    total_empresas = Empresa.query.count()

    total_usuarios = Usuario.query.count()

    total_obras = Obra.query.count()

    total_solicitacoes = Solicitacao.query.count()

    empresas = Empresa.query.order_by(
        Empresa.nome_fantasia.asc(),
        Empresa.razao_social.asc()
    ).all()

    return render_template(
        "admin_dashboard.html",
        total_empresas=total_empresas,
        total_usuarios=total_usuarios,
        total_obras=total_obras,
        total_solicitacoes=total_solicitacoes,
        empresas=empresas
    )


# ============================================================
# NOVA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/nova",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def admin_nova_empresa():

    if request.method == "GET":

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo="Nova empresa"
        )

    razao_social = (
        request.form.get("razao_social")
        or ""
    ).strip()

    nome_fantasia = (
        request.form.get("nome_fantasia")
        or ""
    ).strip()

    cnpj = (
        request.form.get("cnpj")
        or ""
    ).strip()

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
            titulo="Nova empresa"
        )

    # --------------------------------------------------------
    # NORMALIZA CNPJ
    # --------------------------------------------------------

    cnpj_normalizado = (
        cnpj.replace(".", "")
        .replace("/", "")
        .replace("-", "")
        .replace(" ", "")
    )

    if cnpj_normalizado:

        empresas_existentes = Empresa.query.all()

        for existente in empresas_existentes:

            existente_normalizado = (
                (existente.cnpj or "")
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
                .replace(" ", "")
            )

            if (
                existente_normalizado
                and existente_normalizado == cnpj_normalizado
            ):

                flash(
                    "Já existe uma empresa cadastrada com este CNPJ.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    empresa=None,
                    titulo="Nova empresa"
                )

        cnpj_final = cnpj

    else:

        cnpj_final = None

    empresa = Empresa(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia or None,
        cnpj=cnpj_final,
        telefone=telefone or None,
        email=email or None,
        endereco=endereco or None,
        ativo=True
    )

    try:

        db.session.add(
            empresa
        )

        db.session.commit()

    except Exception as erro:

        db.session.rollback()

        print(
            "ERRO AO CADASTRAR EMPRESA:",
            repr(erro)
        )

        flash(
            "Não foi possível cadastrar a empresa. "
            "Verifique se o CNPJ ou outro dado já está cadastrado.",
            "danger"
        )

        return render_template(
            "empresa_form.html",
            empresa=None,
            titulo="Nova empresa"
        )

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


# ============================================================
# DETALHES DA EMPRESA
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
            "danger"
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

    total_usuarios = len(usuarios)

    usuarios_ativos = sum(
        1
        for usuario in usuarios
        if usuario.ativo
    )

    total_obras = len(obras)

    status_inativos = {
        "concluida",
        "concluído",
        "concluída",
        "cancelada",
        "cancelado",
    }

    obras_ativas = sum(
        1
        for obra in obras
        if (
            obra.status
            and obra.status.strip().lower()
            not in status_inativos
        )
    )

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

    administradores_empresa = [
        usuario
        for usuario in usuarios
        if (
            usuario.funcao
            and usuario.funcao.strip().lower()
            in (
                "administrador_empresa",
                "admin_empresa",
            )
        )
    ]

    return render_template(
        "empresa_detalhes.html",
        empresa=empresa,
        usuarios=usuarios,
        obras=obras,
        total_usuarios=total_usuarios,
        usuarios_ativos=usuarios_ativos,
        total_obras=total_obras,
        obras_ativas=obras_ativas,
        total_solicitacoes=total_solicitacoes,
        administradores_empresa=administradores_empresa
    )


# ============================================================
# EDITAR EMPRESA
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
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "GET":

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo="Editar empresa"
        )

    razao_social = (
        request.form.get("razao_social")
        or ""
    ).strip()

    nome_fantasia = (
        request.form.get("nome_fantasia")
        or ""
    ).strip()

    cnpj = (
        request.form.get("cnpj")
        or ""
    ).strip()

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

    ativo = (
        request.form.get("ativo")
        == "on"
    )

    if not razao_social:

        flash(
            "Informe a razão social da empresa.",
            "warning"
        )

        return render_template(
            "empresa_form.html",
            empresa=empresa,
            titulo="Editar empresa"
        )

    cnpj_normalizado = (
        cnpj.replace(".", "")
        .replace("/", "")
        .replace("-", "")
        .replace(" ", "")
    )

    if cnpj_normalizado:

        empresas_existentes = Empresa.query.filter(
            Empresa.id != empresa.id
        ).all()

        for outra in empresas_existentes:

            outro_cnpj = (
                (outra.cnpj or "")
                .replace(".", "")
                .replace("/", "")
                .replace("-", "")
                .replace(" ", "")
            )

            if (
                outro_cnpj
                and outro_cnpj == cnpj_normalizado
            ):

                flash(
                    "Este CNPJ já está cadastrado em outra empresa.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    empresa=empresa,
                    titulo="Editar empresa"
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

    empresa.ativo = ativo

    try:

        db.session.commit()

    except Exception as erro:

        db.session.rollback()

        print(
            "ERRO AO EDITAR EMPRESA:",
            repr(erro)
        )

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
# ATIVAR / DESATIVAR EMPRESA
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
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    empresa.ativo = not empresa.ativo

    try:

        db.session.commit()

    except Exception as erro:

        db.session.rollback()

        print(
            "ERRO AO ALTERAR STATUS DA EMPRESA:",
            repr(erro)
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
            f"A empresa {empresa.nome_fantasia or empresa.razao_social} foi ativada.",
            "success"
        )

    else:

        flash(
            f"A empresa {empresa.nome_fantasia or empresa.razao_social} foi desativada.",
            "warning"
        )

    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# EXCLUIR EMPRESA
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
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    quantidade_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    quantidade_obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    if quantidade_usuarios > 0:

        flash(
            "Esta empresa possui usuários vinculados. "
            "Desative ou remova os usuários antes de excluí-la.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if quantidade_obras > 0:

        flash(
            "Esta empresa possui obras cadastradas. "
            "Remova ou trate as obras antes de excluir a empresa.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    try:

        db.session.delete(
            empresa
        )

        db.session.commit()

    except Exception as erro:

        db.session.rollback()

        print(
            "ERRO AO EXCLUIR EMPRESA:",
            repr(erro)
        )

        flash(
            "Não foi possível excluir a empresa.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    flash(
        "Empresa excluída com sucesso.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# NOVO ADMINISTRADOR DA EMPRESA
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
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if not empresa.ativo:

        flash(
            "Não é possível criar usuários em uma empresa inativa.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        usuario_digitado = (
            request.form.get("usuario")
            or ""
        ).strip()

        senha = (
            request.form.get("senha")
            or ""
        )

        confirmar_senha = (
            request.form.get("confirmacao")
            or request.form.get("confirmar_senha")
            or ""
        )

        if not nome:

            flash(
                "Informe o nome do administrador.",
                "warning"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        if len(usuario_digitado) < 3:

            flash(
                "O usuário deve ter pelo menos 3 caracteres.",
                "warning"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        usuario_digitado = usuario_digitado.lower()

        usuario_existente = Usuario.query.filter(
            db.func.lower(
                Usuario.usuario
            ) == usuario_digitado
        ).first()

        if usuario_existente:

            flash(
                "Este nome de usuário já está sendo utilizado.",
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

        if senha != confirmar_senha:

            flash(
                "As senhas não coincidem.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        novo_usuario = Usuario(
            nome=nome,
            usuario=usuario_digitado,
            funcao="administrador_empresa",
            ativo=True,
            empresa_id=empresa.id
        )

        novo_usuario.definir_senha(
            senha
        )

        try:

            db.session.add(
                novo_usuario
            )

            db.session.commit()

        except Exception as erro:

            db.session.rollback()

            print(
                "ERRO AO CRIAR ADMINISTRADOR:",
                repr(erro)
            )

            flash(
                "Não foi possível criar o administrador. "
                "O nome de usuário pode já estar sendo utilizado.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )

        flash(
            f"Administrador {nome} criado com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "usuario_empresa_form.html",
        empresa=empresa
    )


# ============================================================
# ATIVAR / DESATIVAR USUÁRIO
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
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    usuario = db.session.get(
        Usuario,
        usuario_id
    )

    if not usuario:

        flash(
            "Usuário não encontrado.",
            "danger"
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

    if (
        usuario.funcao
        and usuario.funcao.strip().lower() == "adm"
    ):

        flash(
            "O administrador global não pode ser alterado por este painel.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    eh_admin_empresa_usuario = (
        usuario.funcao
        and usuario.funcao.strip().lower()
        in (
            "administrador_empresa",
            "admin_empresa",
        )
    )

    if usuario.ativo and eh_admin_empresa_usuario:

        outros_admins_ativos = Usuario.query.filter(
            Usuario.empresa_id == empresa.id,
            Usuario.id != usuario.id,
            Usuario.ativo.is_(True),
            db.func.lower(
                Usuario.funcao
            ).in_(
                (
                    "administrador_empresa",
                    "admin_empresa",
                )
            )
        ).count()

        if outros_admins_ativos == 0:

            flash(
                "Não é possível desativar o último administrador ativo da empresa.",
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

    except Exception as erro:

        db.session.rollback()

        print(
            "ERRO AO ALTERAR STATUS DO USUÁRIO:",
            repr(erro)
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
            f"O usuário {usuario.nome} foi ativado.",
            "success"
        )

    else:

        flash(
            f"O usuário {usuario.nome} foi desativado.",
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

    usuario = usuario_atual()

    if eh_administrador():

        return redirect(
            url_for("admin_dashboard")
        )

    empresa = empresa_usuario_atual()

    if empresa:

        obras = Obra.query.filter_by(
            empresa_id=empresa.id
        ).order_by(
            Obra.id.desc()
        ).all()

        total_obras = Obra.query.filter_by(
            empresa_id=empresa.id
        ).count()

        obras_ativas = Obra.query.filter(
            Obra.empresa_id == empresa.id,
            ~db.func.lower(
                Obra.status
            ).in_(
                (
                    "concluida",
                    "concluído",
                    "concluída",
                    "cancelada",
                    "cancelado",
                )
            )
        ).count()

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

        solicitacoes_pendentes = (
            Solicitacao.query
            .join(
                Obra,
                Solicitacao.obra_id == Obra.id
            )
            .filter(
                Obra.empresa_id == empresa.id,
                db.func.lower(
                    Solicitacao.status
                ) == "pendente"
            )
            .count()
        )

        solicitacoes = (
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
            .limit(10)
            .all()
        )

    else:

        obras = Obra.query.order_by(
            Obra.id.desc()
        ).all()

        total_obras = Obra.query.count()

        obras_ativas = Obra.query.filter(
            ~db.func.lower(
                Obra.status
            ).in_(
                (
                    "concluida",
                    "concluído",
                    "concluída",
                    "cancelada",
                    "cancelado",
                )
            )
        ).count()

        total_solicitacoes = Solicitacao.query.count()

        solicitacoes_pendentes = (
            Solicitacao.query.filter(
                db.func.lower(
                    Solicitacao.status
                ) == "pendente"
            ).count()
        )

        solicitacoes = (
            Solicitacao.query
            .order_by(
                Solicitacao.id.desc()
            )
            .limit(10)
            .all()
        )

    return render_template(
        "dashboard.html",
        usuario=usuario,
        empresa=empresa,
        obras=obras,
        total_obras=total_obras,
        obras_ativas=obras_ativas,
        total_solicitacoes=total_solicitacoes,
        solicitacoes_pendentes=solicitacoes_pendentes,
        solicitacoes=solicitacoes
    )


# ============================================================
# OBRAS
# ============================================================

@app.route("/obras")
@login_obrigatorio
def obras():

    empresa = empresa_usuario_atual()

    if empresa:

        lista_obras = Obra.query.filter_by(
            empresa_id=empresa.id
        ).order_by(
            Obra.id.desc()
        ).all()

    else:

        lista_obras = Obra.query.order_by(
            Obra.id.desc()
        ).all()

    return render_template(
        "obras.html",
        obras=lista_obras
    )


@app.route(
    "/obras/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def nova_obra():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Não foi possível identificar a empresa.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
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

        responsavel = (
            request.form.get("responsavel")
            or ""
        ).strip()

        endereco = (
            request.form.get("endereco")
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
        ).strip()

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
                "obra_form.html"
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
                "obra_form.html"
            )

        if (
            data_inicio
            and previsao_termino
            and previsao_termino < data_inicio
        ):

            flash(
                "A previsão de término não pode ser anterior ao início da obra.",
                "warning"
            )

            return render_template(
                "obra_form.html"
            )

        obra = Obra(
            empresa_id=empresa.id,
            nome=nome,
            cliente=cliente or None,
            responsavel=responsavel or None,
            endereco=endereco or None,
            data_inicio=data_inicio,
            previsao_termino=previsao_termino,
            status=status or "planejamento",
            observacoes=observacoes or None
        )

        try:

            db.session.add(obra)

            db.session.commit()

        except Exception as erro:

            db.session.rollback()

            print(
                "ERRO AO CADASTRAR OBRA:",
                repr(erro)
            )

            flash(
                "Não foi possível cadastrar a obra.",
                "danger"
            )

            return render_template(
                "obra_form.html"
            )

        flash(
            "Obra cadastrada com sucesso.",
            "success"
        )

        return redirect(
            url_for("obras")
        )

    return render_template(
        "obra_form.html"
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

        unidade = (
            request.form.get("unidade")
            or ""
        ).strip()

        descricao = (
            request.form.get("descricao")
            or ""
        ).strip()

        estoque_minimo_str = (
            request.form.get("estoque_minimo")
            or "0"
        ).strip()

        estoque_atual_str = (
            request.form.get("estoque_atual")
            or "0"
        ).strip()

        ativo = (
            request.form.get("ativo")
            == "on"
        )

        if not categoria:

            flash(
                "Informe a categoria do material.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        if not nome:

            flash(
                "Informe o nome do material.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        if not unidade:

            flash(
                "Informe a unidade do material.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        try:

            estoque_minimo = float(
                estoque_minimo_str.replace(",", ".")
            )

            estoque_atual = float(
                estoque_atual_str.replace(",", ".")
            )

        except (ValueError, TypeError):

            flash(
                "Informe valores de estoque válidos.",
                "danger"
            )

            return render_template(
                "material_form.html"
            )

        if (
            estoque_minimo < 0
            or estoque_atual < 0
        ):

            flash(
                "Os valores de estoque não podem ser negativos.",
                "warning"
            )

            return render_template(
                "material_form.html"
            )

        material = Material(
            categoria=categoria,
            nome=nome,
            unidade=unidade,
            descricao=descricao or None,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual,
            ativo=ativo
        )

        try:

            db.session.add(material)

            db.session.commit()

        except Exception as erro:

            db.session.rollback()

            print(
                "ERRO AO CADASTRAR MATERIAL:",
                repr(erro)
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

    empresa = empresa_usuario_atual()

    if empresa:

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

    else:

        lista_solicitacoes = (
            Solicitacao.query
            .order_by(
                Solicitacao.id.desc()
            )
            .all()
        )

    return render_template(
        "solicitacoes.html",
        solicitacoes=lista_solicitacoes
    )


@app.route(
    "/solicitacoes/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def nova_solicitacao():

    empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Não foi possível identificar a empresa.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        obra_id_str = (
            request.form.get("obra_id")
            or ""
        ).strip()

        material_id_str = (
            request.form.get("material_id")
            or ""
        ).strip()

        quantidade_str = (
            request.form.get("quantidade")
            or ""
        ).strip()

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
                quantidade_str.replace(",", ".")
            )

        except (ValueError, TypeError):

            flash(
                "Preencha corretamente os dados da solicitação.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if quantidade <= 0:

            flash(
                "A quantidade deve ser maior que zero.",
                "warning"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        obra = Obra.query.filter_by(
            id=obra_id,
            empresa_id=empresa.id
        ).first()

        if not obra:

            flash(
                "Obra inválida ou não pertence à sua empresa.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        material = db.session.get(
            Material,
            material_id
        )

        if not material or not material.ativo:

            flash(
                "Material inválido ou inativo.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        usuario = usuario_atual()

        solicitacao = Solicitacao(
            obra_id=obra.id,
            material_id=material.id,
            usuario_id=usuario.id,
            quantidade=quantidade,
            observacao=observacao or None,
            status="pendente"
        )

        try:

            db.session.add(
                solicitacao
            )

            db.session.commit()

        except Exception as erro:

            db.session.rollback()

            print(
                "ERRO AO CRIAR SOLICITAÇÃO:",
                repr(erro)
            )

            flash(
                "Não foi possível criar a solicitação.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        flash(
            "Solicitação de material enviada com sucesso.",
            "success"
        )

        return redirect(
            url_for("solicitacoes")
        )

    obras_disponiveis = Obra.query.filter_by(
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

    return render_template(
        "solicitacao_form.html",
        obras=obras_disponiveis,
        materiais=materiais_disponiveis
    )


# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    try:

        return render_template(
            "error.html",
            codigo=404,
            titulo="Página não encontrada",
            mensagem="A página que você tentou acessar não existe."
        ), 404

    except Exception:

        return (
            "<h1>404 - Página não encontrada</h1>",
            404
        )


@app.errorhandler(500)
def erro_servidor(error):

    try:

        db.session.rollback()

    except Exception:

        pass

    print(
        "ERRO 500:",
        repr(error)
    )

    try:

        return render_template(
            "error.html",
            codigo=500,
            titulo="Erro interno",
            mensagem=(
                "Ocorreu um erro interno no sistema. "
                "A operação não foi concluída."
            )
        ), 500

    except Exception:

        return (
            "<h1>500 - Erro interno do servidor</h1>",
            500
        )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

inicializar_banco()


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
