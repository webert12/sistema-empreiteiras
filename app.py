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

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    razao_social = db.Column(
        db.String(150),
        nullable=False
    )

    nome_fantasia = db.Column(
        db.String(150),
        nullable=False
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
        db.String(255),
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


class Usuario(db.Model):
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

    id = db.Column(
        db.Integer,
        primary_key=True
    )

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
    """
    Retorna o usuário atualmente autenticado.
    """

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    return db.session.get(
        Usuario,
        usuario_id
    )


def eh_administrador():
    """
    Verifica se o usuário atual é o ADM global da plataforma.
    """

    usuario = usuario_atual()

    if not usuario:
        return False

    return (
        usuario.funcao
        and usuario.funcao.strip().lower() == "adm"
    )


def login_obrigatorio(func):
    """
    Protege rotas que exigem autenticação.
    """

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

        # ----------------------------------------------------
        # BLOQUEIO DE EMPRESA INATIVA
        # ----------------------------------------------------

        if (
            usuario.empresa_id
            and not eh_administrador()
        ):

            empresa = db.session.get(
                Empresa,
                usuario.empresa_id
            )

            if not empresa or not empresa.ativo:

                session.clear()

                flash(
                    "A empresa vinculada ao seu usuário "
                    "está desativada.",
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

        return func(*args, **kwargs)

    return wrapper


def admin_obrigatorio():
    """
    Protege áreas exclusivas do administrador global.

    Retorna uma resposta Flask quando o acesso deve ser bloqueado.
    Retorna None quando o usuário pode continuar.
    """

    usuario = usuario_atual()

    if not usuario:

        flash(
            "Faça login para acessar a administração.",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    if not usuario.ativo:

        session.clear()

        flash(
            "Usuário desativado.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    if not eh_administrador():

        flash(
            "Acesso restrito ao administrador da plataforma.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    return None


@app.context_processor
def dados_globais():

    usuario = usuario_atual()

    return {
        "usuario_logado": usuario,

        "usuario_eh_admin": (
            usuario is not None
            and usuario.funcao
            and usuario.funcao.strip().lower() == "adm"
        )
    }


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    with app.app_context():

        db.create_all()

        # ----------------------------------------------------
        # EMPRESA PADRÃO
        # ----------------------------------------------------

        empresa = Empresa.query.first()

        if not empresa:

            empresa = Empresa(
                razao_social="Empresa de Construção",
                nome_fantasia="Construtora",
                ativo=True
            )

            db.session.add(
                empresa
            )

            db.session.commit()


        # ----------------------------------------------------
        # ADMINISTRADOR GLOBAL
        # ----------------------------------------------------

        admin_usuario = os.getenv(
            "ADMIN_USER",
            "admin"
        ).strip()

        admin_senha = os.getenv(
            "ADMIN_PASSWORD",
            ""
        )


        usuario = Usuario.query.filter_by(
            usuario=admin_usuario
        ).first()


        # ----------------------------------------------------
        # SE O ADM JÁ EXISTIR
        # ----------------------------------------------------

        if usuario:

            alterou = False


            if (
                not usuario.funcao
                or usuario.funcao.strip().lower() != "adm"
            ):

                usuario.funcao = "ADM"

                alterou = True


            if usuario.empresa_id is not None:

                usuario.empresa_id = None

                alterou = True


            if not usuario.ativo:

                usuario.ativo = True

                alterou = True


            # A senha existente NÃO é alterada automaticamente.
            # Isso evita trocar a senha do administrador a cada deploy.


            if alterou:

                db.session.commit()


        # ----------------------------------------------------
        # SE O ADM AINDA NÃO EXISTIR
        # ----------------------------------------------------

        elif admin_senha:

            usuario = Usuario(
                nome="Administrador da Plataforma",
                usuario=admin_usuario,
                funcao="ADM",
                empresa_id=None,
                ativo=True
            )

            usuario.definir_senha(
                admin_senha
            )

            db.session.add(
                usuario
            )

            db.session.commit()


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if session.get("usuario_id"):

        usuario = usuario_atual()

        if usuario and usuario.ativo:

            # ADM GLOBAL
            if eh_administrador():

                return redirect(
                    url_for("admin_dashboard")
                )

            # Usuário de empresa
            if usuario.empresa_id:

                empresa = db.session.get(
                    Empresa,
                    usuario.empresa_id
                )

                if empresa and empresa.ativo:

                    return redirect(
                        url_for("dashboard")
                    )

                session.clear()

            else:

                return redirect(
                    url_for("dashboard")
                )

        session.clear()


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

            # ------------------------------------------------
            # VERIFICA EMPRESA DO USUÁRIO
            # ------------------------------------------------

            if usuario.empresa_id:

                empresa = db.session.get(
                    Empresa,
                    usuario.empresa_id
                )

                if not empresa or not empresa.ativo:

                    flash(
                        "A empresa vinculada a este usuário "
                        "está desativada.",
                        "danger"
                    )

                    return redirect(
                        url_for("login")
                    )


            session.clear()

            session["usuario_id"] = usuario.id


            if eh_administrador():

                return redirect(
                    url_for("admin_dashboard")
                )


            return redirect(
                url_for("dashboard")
            )


        flash(
            "Usuário ou senha inválidos.",
            "danger"
        )


    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

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
# PAINEL ADMINISTRATIVO GLOBAL
# ============================================================

@app.route("/admin")
@login_obrigatorio
def admin_dashboard():

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    # --------------------------------------------------------
    # INDICADORES GERAIS
    # --------------------------------------------------------

    total_empresas = Empresa.query.count()

    total_usuarios = Usuario.query.count()

    total_obras = Obra.query.count()

    total_solicitacoes = Solicitacao.query.count()


    # --------------------------------------------------------
    # EMPRESAS
    # --------------------------------------------------------

    empresas = Empresa.query.order_by(
        Empresa.nome_fantasia.asc()
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
# ADMIN - NOVA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/nova",
    methods=["GET", "POST"]
)
@login_obrigatorio
def admin_nova_empresa():

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    if request.method == "POST":

        razao_social = request.form.get(
            "razao_social",
            ""
        ).strip()


        nome_fantasia = request.form.get(
            "nome_fantasia",
            ""
        ).strip()


        cnpj = request.form.get(
            "cnpj",
            ""
        ).strip()


        telefone = request.form.get(
            "telefone",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip()


        endereco = request.form.get(
            "endereco",
            ""
        ).strip()


        # ----------------------------------------------------
        # VALIDAÇÃO
        # ----------------------------------------------------

        if not razao_social:

            flash(
                "Informe a razão social da empresa.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                titulo="Nova empresa",
                empresa=None
            )


        # Nome fantasia é obrigatório no banco.
        if not nome_fantasia:

            nome_fantasia = razao_social


        # ----------------------------------------------------
        # CNPJ DUPLICADO
        # ----------------------------------------------------

        if cnpj:

            empresa_existente = Empresa.query.filter_by(
                cnpj=cnpj
            ).first()


            if empresa_existente:

                flash(
                    "Já existe uma empresa cadastrada "
                    "com este CNPJ.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    titulo="Nova empresa",
                    empresa=None
                )


        # ----------------------------------------------------
        # CRIA EMPRESA
        # ----------------------------------------------------

        empresa = Empresa(

            razao_social=razao_social,

            nome_fantasia=nome_fantasia,

            cnpj=cnpj or None,

            telefone=telefone or None,

            email=email or None,

            endereco=endereco or None,

            ativo=True
        )


        db.session.add(
            empresa
        )

        db.session.commit()


        flash(
            f'Empresa "{empresa.nome_fantasia}" '
            "cadastrada com sucesso.",
            "success"
        )


        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )


    return render_template(
        "empresa_form.html",
        titulo="Nova empresa",
        empresa=None
    )


# ============================================================
# ADMIN - VISUALIZAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>"
)
@login_obrigatorio
def admin_empresa_detalhes(empresa_id):

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    empresa = Empresa.query.get_or_404(
        empresa_id
    )


    # --------------------------------------------------------
    # USUÁRIOS DA EMPRESA
    # --------------------------------------------------------

    usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Usuario.nome.asc()
    ).all()


    # --------------------------------------------------------
    # ADMINISTRADORES DA EMPRESA
    # --------------------------------------------------------

    administradores = Usuario.query.filter_by(
        empresa_id=empresa.id,
        funcao="administrador_empresa"
    ).order_by(
        Usuario.nome.asc()
    ).all()


    # --------------------------------------------------------
    # OBRAS DA EMPRESA
    # --------------------------------------------------------

    obras = Obra.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Obra.criado_em.desc()
    ).all()


    # --------------------------------------------------------
    # INDICADORES
    # --------------------------------------------------------

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()


    total_obras = Obra.query.filter_by(
        empresa_id=empresa.id
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


    return render_template(
        "empresa_detalhes.html",

        empresa=empresa,

        usuarios=usuarios,

        administradores=administradores,

        obras=obras,

        total_usuarios=total_usuarios,

        total_obras=total_obras,

        total_solicitacoes=total_solicitacoes
    )


# ============================================================
# ADMIN - EDITAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"]
)
@login_obrigatorio
def admin_editar_empresa(empresa_id):

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    empresa = Empresa.query.get_or_404(
        empresa_id
    )


    if request.method == "POST":

        razao_social = request.form.get(
            "razao_social",
            ""
        ).strip()


        nome_fantasia = request.form.get(
            "nome_fantasia",
            ""
        ).strip()


        cnpj = request.form.get(
            "cnpj",
            ""
        ).strip()


        telefone = request.form.get(
            "telefone",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip()


        endereco = request.form.get(
            "endereco",
            ""
        ).strip()


        # ----------------------------------------------------
        # VALIDAÇÃO
        # ----------------------------------------------------

        if not razao_social:

            flash(
                "A razão social é obrigatória.",
                "danger"
            )

            return render_template(
                "empresa_form.html",
                titulo="Editar empresa",
                empresa=empresa
            )


        if not nome_fantasia:

            nome_fantasia = razao_social


        # ----------------------------------------------------
        # VERIFICA CNPJ
        # ----------------------------------------------------

        if cnpj:

            empresa_existente = Empresa.query.filter(
                Empresa.cnpj == cnpj,
                Empresa.id != empresa.id
            ).first()


            if empresa_existente:

                flash(
                    "Já existe outra empresa cadastrada "
                    "com este CNPJ.",
                    "danger"
                )

                return render_template(
                    "empresa_form.html",
                    titulo="Editar empresa",
                    empresa=empresa
                )


        # ----------------------------------------------------
        # ATUALIZA DADOS
        # ----------------------------------------------------

        empresa.razao_social = razao_social

        empresa.nome_fantasia = nome_fantasia

        empresa.cnpj = cnpj or None

        empresa.telefone = telefone or None

        empresa.email = email or None

        empresa.endereco = endereco or None


        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        # Só altera o status se o campo estiver presente.
        if "ativo" in request.form:

            empresa.ativo = (
                request.form.get("ativo") == "on"
            )


        db.session.commit()


        flash(
            "Dados da empresa atualizados com sucesso.",
            "success"
        )


        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )


    return render_template(
        "empresa_form.html",
        titulo="Editar empresa",
        empresa=empresa
    )


# ============================================================
# ADMIN - ATIVAR / DESATIVAR EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/alternar-status",
    methods=["POST"]
)
@login_obrigatorio
def admin_alternar_empresa(empresa_id):

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    empresa = Empresa.query.get_or_404(
        empresa_id
    )


    empresa.ativo = not empresa.ativo


    db.session.commit()


    if empresa.ativo:

        flash(
            f'Empresa "{empresa.nome_fantasia}" '
            "ativada com sucesso.",
            "success"
        )

    else:

        flash(
            f'Empresa "{empresa.nome_fantasia}" '
            "desativada com sucesso.",
            "warning"
        )


    return redirect(
        url_for(
            "admin_empresa_detalhes",
            empresa_id=empresa.id
        )
    )


# ============================================================
# ADMIN - NOVO ADMINISTRADOR DA EMPRESA
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/novo-administrador",
    methods=["GET", "POST"]
)
@login_obrigatorio
def admin_novo_usuario_empresa(empresa_id):

    bloqueio = admin_obrigatorio()

    if bloqueio:

        return bloqueio


    empresa = Empresa.query.get_or_404(
        empresa_id
    )


    # --------------------------------------------------------
    # EMPRESA DESATIVADA
    # --------------------------------------------------------

    if not empresa.ativo:

        flash(
            "Não é possível criar um administrador "
            "para uma empresa desativada.",
            "warning"
        )

        return redirect(
            url_for(
                "admin_empresa_detalhes",
                empresa_id=empresa.id
            )
        )


    if request.method == "POST":

        nome = request.form.get(
            "nome",
            ""
        ).strip()


        usuario_digitado = request.form.get(
            "usuario",
            ""
        ).strip().lower()


        senha = request.form.get(
            "senha",
            ""
        )


        confirmar_senha = request.form.get(
            "confirmar_senha",
            ""
        )


        # ----------------------------------------------------
        # NOME
        # ----------------------------------------------------

        if not nome:

            flash(
                "Informe o nome do administrador.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )


        # ----------------------------------------------------
        # USUÁRIO
        # ----------------------------------------------------

        if len(usuario_digitado) < 3:

            flash(
                "O usuário precisa ter pelo menos "
                "3 caracteres.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )


        # ----------------------------------------------------
        # USUÁRIO DUPLICADO
        # ----------------------------------------------------

        usuario_existente = Usuario.query.filter_by(
            usuario=usuario_digitado
        ).first()


        if usuario_existente:

            flash(
                "Esse nome de usuário já está sendo utilizado.",
                "danger"
            )

            return render_template(
                "usuario_empresa_form.html",
                empresa=empresa
            )


        # ----------------------------------------------------
        # SENHA
        # ----------------------------------------------------

        if len(senha) < 6:

            flash(
                "A senha precisa ter pelo menos "
                "6 caracteres.",
                "danger"
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


        # ----------------------------------------------------
        # CRIA ADMINISTRADOR
        # ----------------------------------------------------

        novo_usuario = Usuario(

            nome=nome,

            usuario=usuario_digitado,

            empresa_id=empresa.id,

            funcao="administrador_empresa",

            ativo=True
        )


        novo_usuario.definir_senha(
            senha
        )


        db.session.add(
            novo_usuario
        )

        db.session.commit()


        flash(
            f'Administrador "{nome}" criado com sucesso '
            f'para {empresa.nome_fantasia}.',
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
# DASHBOARD DA EMPRESA
# ============================================================

@app.route("/")
@login_obrigatorio
def dashboard():

    usuario = usuario_atual()


    # ADM utiliza o painel global.
    if eh_administrador():

        return redirect(
            url_for("admin_dashboard")
        )


    # --------------------------------------------------------
    # OBRAS DA EMPRESA
    # --------------------------------------------------------

    obras_query = Obra.query


    if usuario.empresa_id:

        obras_query = obras_query.filter_by(
            empresa_id=usuario.empresa_id
        )

    else:

        obras_query = obras_query.filter(
            Obra.id == -1
        )


    obras = obras_query.all()


    total_obras = len(
        obras
    )


    obras_ativas = sum(
        1
        for obra in obras
        if obra.status in (
            "andamento",
            "em andamento"
        )
    )


    # --------------------------------------------------------
    # MATERIAIS
    # --------------------------------------------------------

    total_materiais = Material.query.filter_by(
        ativo=True
    ).count()


    materiais_baixos = Material.query.filter(
        Material.ativo.is_(True),
        Material.estoque_atual <= Material.estoque_minimo
    ).count()


    # --------------------------------------------------------
    # SOLICITAÇÕES PENDENTES
    # --------------------------------------------------------

    if usuario.empresa_id:

        solicitacoes_pendentes = (
            Solicitacao.query
            .join(
                Obra,
                Solicitacao.obra_id == Obra.id
            )
            .filter(
                Obra.empresa_id == usuario.empresa_id,
                Solicitacao.status == "pendente"
            )
            .count()
        )

    else:

        solicitacoes_pendentes = 0


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


    # ADM trabalha pelo painel administrativo.
    if eh_administrador():

        return redirect(
            url_for("admin_dashboard")
        )


    query = Obra.query


    if usuario.empresa_id:

        query = query.filter_by(
            empresa_id=usuario.empresa_id
        )

    else:

        query = query.filter(
            Obra.id == -1
        )


    lista = query.order_by(
        Obra.id.desc()
    ).all()


    return render_template(
        "obras.html",
        obras=lista
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

    usuario = usuario_atual()


    # --------------------------------------------------------
    # ADM
    # --------------------------------------------------------

    if eh_administrador():

        flash(
            "Selecione uma empresa pelo painel administrativo "
            "para cadastrar uma obra.",
            "info"
        )

        return redirect(
            url_for("admin_dashboard")
        )


    # --------------------------------------------------------
    # USUÁRIO SEM EMPRESA
    # --------------------------------------------------------

    if not usuario.empresa_id:

        flash(
            "Seu usuário não está vinculado a uma empresa.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


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


        # ----------------------------------------------------
        # DATAS
        # ----------------------------------------------------

        data_inicio = None

        previsao_termino = None


        data_inicio_texto = request.form.get(
            "data_inicio",
            ""
        ).strip()


        previsao_termino_texto = request.form.get(
            "previsao_termino",
            ""
        ).strip()


        try:

            if data_inicio_texto:

                data_inicio = datetime.strptime(
                    data_inicio_texto,
                    "%Y-%m-%d"
                ).date()


            if previsao_termino_texto:

                previsao_termino = datetime.strptime(
                    previsao_termino_texto,
                    "%Y-%m-%d"
                ).date()


        except ValueError:

            flash(
                "Uma das datas informadas é inválida.",
                "danger"
            )

            return redirect(
                url_for("nova_obra")
            )


        if (
            data_inicio
            and previsao_termino
            and previsao_termino < data_inicio
        ):

            flash(
                "A previsão de término não pode ser anterior "
                "à data de início.",
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

            data_inicio=data_inicio,

            previsao_termino=previsao_termino,

            status=request.form.get(
                "status",
                "planejamento"
            ),

            observacoes=request.form.get(
                "observacoes",
                ""
            ).strip()
        )


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

    # O catálogo de materiais é global neste momento.
    # Nenhum preço é armazenado.

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


# ============================================================
# NOVO MATERIAL
# ============================================================

@app.route(
    "/materiais/novo",
    methods=["GET", "POST"]
)
@login_obrigatorio
def novo_material():

    # Cadastro global será posteriormente
    # controlado pelo módulo administrativo.

    if eh_administrador():

        flash(
            "O cadastro global de materiais será realizado "
            "pelo módulo administrativo.",
            "info"
        )

        return redirect(
            url_for("admin_dashboard")
        )


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


        if estoque_minimo < 0 or estoque_atual < 0:

            flash(
                "Os valores de estoque não podem ser negativos.",
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

            estoque_atual=estoque_atual,

            ativo=True
        )


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


    # ADM visualiza o painel global.
    if eh_administrador():

        return redirect(
            url_for("admin_dashboard")
        )


    query = Solicitacao.query


    if usuario.empresa_id:

        query = query.join(
            Obra,
            Solicitacao.obra_id == Obra.id
        ).filter(
            Obra.empresa_id == usuario.empresa_id
        )

    else:

        query = query.filter(
            Solicitacao.id == -1
        )


    lista = query.order_by(
        Solicitacao.id.desc()
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
@login_obrigatorio
def nova_solicitacao():

    usuario = usuario_atual()


    if eh_administrador():

        flash(
            "O ADM deve selecionar uma empresa antes "
            "de criar uma solicitação.",
            "info"
        )

        return redirect(
            url_for("admin_dashboard")
        )


    if not usuario.empresa_id:

        flash(
            "Seu usuário não está vinculado a uma empresa.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


    # --------------------------------------------------------
    # OBRAS DA EMPRESA
    # --------------------------------------------------------

    obras = Obra.query.filter_by(
        empresa_id=usuario.empresa_id
    ).order_by(
        Obra.nome
    ).all()


    # --------------------------------------------------------
    # MATERIAIS ATIVOS
    # --------------------------------------------------------

    materiais = Material.query.filter_by(
        ativo=True
    ).order_by(
        Material.nome
    ).all()


    if request.method == "POST":

        try:

            obra_id = int(
                request.form.get(
                    "obra_id"
                )
            )


            material_id = int(
                request.form.get(
                    "material_id"
                )
            )


            quantidade = float(
                request.form.get(
                    "quantidade"
                )
            )


        except (
            ValueError,
            TypeError
        ):

            flash(
                "Dados da solicitação inválidos.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )


        # ----------------------------------------------------
        # VALIDA OBRA
        # ----------------------------------------------------

        obra = db.session.get(
            Obra,
            obra_id
        )


        if (
            not obra
            or obra.empresa_id != usuario.empresa_id
        ):

            flash(
                "Obra inválida.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )


        # ----------------------------------------------------
        # VALIDA MATERIAL
        # ----------------------------------------------------

        material = db.session.get(
            Material,
            material_id
        )


        if (
            not material
            or not material.ativo
        ):

            flash(
                "Material inválido.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )


        # ----------------------------------------------------
        # VALIDA QUANTIDADE
        # ----------------------------------------------------

        if quantidade <= 0:

            flash(
                "A quantidade deve ser maior que zero.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )


        # ----------------------------------------------------
        # CRIA SOLICITAÇÃO
        # ----------------------------------------------------

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


        db.session.add(
            solicitacao
        )

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
# ERRO 404
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(error):

    return render_template(
        "404.html"
    ), 404


# ============================================================
# ERRO 500
# ============================================================

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


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

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
