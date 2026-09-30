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
    jsonify,
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

login_manager.login_message = (
    "Faça login para acessar esta página."
)

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


# ============================================================
# CATÁLOGO DE MATERIAIS
# ============================================================

MATERIAIS_CATALOGO = [

    (
        "Agregados",
        "Areia média",
        "m³",
        "Areia média para argamassa e concreto."
    ),

    (
        "Agregados",
        "Areia fina",
        "m³",
        "Areia fina para acabamento e argamassa."
    ),

    (
        "Agregados",
        "Areia grossa",
        "m³",
        "Areia grossa para concreto."
    ),

    (
        "Agregados",
        "Brita 0",
        "m³",
        "Brita fina para concretos e acabamentos."
    ),

    (
        "Agregados",
        "Brita 1",
        "m³",
        "Brita para concreto estrutural."
    ),

    (
        "Agregados",
        "Brita 2",
        "m³",
        "Brita para concreto e fundações."
    ),

    (
        "Agregados",
        "Pedrisco",
        "m³",
        "Agregado miúdo para concretos e pavimentação."
    ),

    (
        "Agregados",
        "Pó de pedra",
        "m³",
        "Material para bases, pisos e regularização."
    ),

    (
        "Agregados",
        "Rachão",
        "m³",
        "Pedra bruta para fundações e bases."
    ),

    (
        "Agregados",
        "Seixo rolado",
        "m³",
        "Agregado para drenagem e concreto."
    ),

    (
        "Cimento e argamassas",
        "Cimento CP II 32",
        "saco",
        "Cimento Portland para uso geral."
    ),

    (
        "Cimento e argamassas",
        "Cimento CP II 40",
        "saco",
        "Cimento Portland para uso geral e estrutural."
    ),

    (
        "Cimento e argamassas",
        "Cimento CP III",
        "saco",
        "Cimento Portland de alto-forno."
    ),

    (
        "Cimento e argamassas",
        "Cal hidratada",
        "saco",
        "Cal hidratada para argamassas."
    ),

    (
        "Cimento e argamassas",
        "Cal virgem",
        "saco",
        "Cal virgem para preparo de argamassa."
    ),

    (
        "Cimento e argamassas",
        "Argamassa AC-I",
        "saco",
        "Argamassa colante para áreas internas."
    ),

    (
        "Cimento e argamassas",
        "Argamassa AC-II",
        "saco",
        "Argamassa colante para áreas internas e externas."
    ),

    (
        "Cimento e argamassas",
        "Argamassa AC-III",
        "saco",
        "Argamassa de alta aderência."
    ),

    (
        "Cimento e argamassas",
        "Argamassa de assentamento",
        "saco",
        "Argamassa pronta para alvenaria."
    ),

    (
        "Cimento e argamassas",
        "Argamassa de revestimento",
        "saco",
        "Argamassa pronta para revestimento."
    ),

    (
        "Cimento e argamassas",
        "Rejunte cimentício",
        "kg",
        "Rejunte para pisos e revestimentos."
    ),

    (
        "Cimento e argamassas",
        "Rejunte epóxi",
        "kg",
        "Rejunte epóxi para áreas de maior exigência."
    ),

    (
        "Concreto",
        "Concreto usinado",
        "m³",
        "Concreto usinado conforme especificação da obra."
    ),

    (
        "Concreto",
        "Aditivo plastificante",
        "L",
        "Aditivo para melhorar trabalhabilidade do concreto."
    ),

    (
        "Concreto",
        "Aditivo impermeabilizante",
        "L",
        "Aditivo para redução de absorção de água."
    ),

    (
        "Concreto",
        "Graute",
        "saco",
        "Graute para preenchimento e reforço."
    ),

    (
        "Concreto",
        "Fibra para concreto",
        "kg",
        "Fibra para reforço e controle de fissuras."
    ),

    (
        "Alvenaria",
        "Bloco cerâmico 9 cm",
        "un",
        "Bloco cerâmico para vedação."
    ),

    (
        "Alvenaria",
        "Bloco cerâmico 11,5 cm",
        "un",
        "Bloco cerâmico para vedação."
    ),

    (
        "Alvenaria",
        "Bloco cerâmico 14 cm",
        "un",
        "Bloco cerâmico para vedação."
    ),

    (
        "Alvenaria",
        "Bloco de concreto 9 cm",
        "un",
        "Bloco de concreto para vedação."
    ),

    (
        "Alvenaria",
        "Bloco de concreto 14 cm",
        "un",
        "Bloco de concreto para vedação."
    ),

    (
        "Alvenaria",
        "Bloco de concreto 19 cm",
        "un",
        "Bloco de concreto para alvenaria."
    ),

    (
        "Alvenaria",
        "Tijolo maciço",
        "un",
        "Tijolo cerâmico maciço."
    ),

    (
        "Alvenaria",
        "Canaleta cerâmica",
        "un",
        "Canaleta para vergas, contravergas e cintas."
    ),

    (
        "Alvenaria",
        "Canaleta de concreto",
        "un",
        "Canaleta para elementos de concreto."
    ),

    (
        "Alvenaria",
        "Tela para alvenaria",
        "m",
        "Tela metálica para reforço de alvenaria."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 4,2 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 5 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 6,3 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 8 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 10 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 12,5 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Vergalhão CA-50 16 mm",
        "barra",
        "Aço para armaduras."
    ),

    (
        "Aço e ferragens",
        "Arame recozido",
        "kg",
        "Arame para amarração de ferragens."
    ),

    (
        "Aço e ferragens",
        "Estribo 4,2 mm",
        "un",
        "Estribo para armação de pilares e vigas."
    ),

    (
        "Aço e ferragens",
        "Estribo 5 mm",
        "un",
        "Estribo para armação de pilares e vigas."
    ),

    (
        "Aço e ferragens",
        "Tela soldada",
        "m²",
        "Tela de aço para pisos e estruturas."
    ),

    (
        "Aço e ferragens",
        "Prego 17x27",
        "kg",
        "Prego para carpintaria."
    ),

    (
        "Aço e ferragens",
        "Prego 18x27",
        "kg",
        "Prego para carpintaria."
    ),

    (
        "Aço e ferragens",
        "Prego 19x36",
        "kg",
        "Prego para carpintaria."
    ),

    (
        "Madeira",
        "Sarrafo de madeira",
        "m",
        "Sarrafo para formas e estruturas."
    ),

    (
        "Madeira",
        "Caibro de madeira",
        "m",
        "Caibro para cobertura e estruturas."
    ),

    (
        "Madeira",
        "Ripa de madeira",
        "m",
        "Ripa para cobertura e acabamentos."
    ),

    (
        "Madeira",
        "Tábua de madeira",
        "m",
        "Tábua para formas e estruturas."
    ),

    (
        "Madeira",
        "Compensado para forma",
        "chapa",
        "Chapa para formas de concreto."
    ),

    (
        "Madeira",
        "Madeirite",
        "chapa",
        "Chapa de madeira para formas e divisórias."
    ),

    (
        "Impermeabilização",
        "Manta asfáltica",
        "m²",
        "Manta para impermeabilização."
    ),

    (
        "Impermeabilização",
        "Impermeabilizante cimentício",
        "kg",
        "Produto cimentício para impermeabilização."
    ),

    (
        "Impermeabilização",
        "Emulsão asfáltica",
        "kg",
        "Impermeabilizante para fundações e áreas externas."
    ),

    (
        "Impermeabilização",
        "Selante PU",
        "cartucho",
        "Selante de poliuretano."
    ),

    (
        "Hidráulica",
        "Tubo PVC água 20 mm",
        "barra",
        "Tubo para instalações de água fria."
    ),

    (
        "Hidráulica",
        "Tubo PVC água 25 mm",
        "barra",
        "Tubo para instalações de água fria."
    ),

    (
        "Hidráulica",
        "Tubo PVC água 32 mm",
        "barra",
        "Tubo para instalações de água fria."
    ),

    (
        "Hidráulica",
        "Tubo PVC esgoto 40 mm",
        "barra",
        "Tubo para esgoto."
    ),

    (
        "Hidráulica",
        "Tubo PVC esgoto 50 mm",
        "barra",
        "Tubo para esgoto."
    ),

    (
        "Hidráulica",
        "Tubo PVC esgoto 75 mm",
        "barra",
        "Tubo para esgoto."
    ),

    (
        "Hidráulica",
        "Tubo PVC esgoto 100 mm",
        "barra",
        "Tubo para esgoto."
    ),

    (
        "Hidráulica",
        "Joelho PVC 90° 25 mm",
        "un",
        "Conexão hidráulica."
    ),

    (
        "Hidráulica",
        "Joelho PVC 90° 50 mm",
        "un",
        "Conexão para esgoto."
    ),

    (
        "Hidráulica",
        "Tê PVC 25 mm",
        "un",
        "Conexão hidráulica."
    ),

    (
        "Hidráulica",
        "Tê PVC 50 mm",
        "un",
        "Conexão para esgoto."
    ),

    (
        "Hidráulica",
        "Registro de pressão",
        "un",
        "Registro para controle de água."
    ),

    (
        "Hidráulica",
        "Caixa sifonada",
        "un",
        "Caixa para drenagem de ambientes."
    ),

    (
        "Hidráulica",
        "Ralo PVC",
        "un",
        "Ralo para drenagem."
    ),

    (
        "Hidráulica",
        "Cola para PVC",
        "g",
        "Adesivo para tubos e conexões de PVC."
    ),

    (
        "Elétrica",
        "Fio 1,5 mm²",
        "m",
        "Condutor elétrico."
    ),

    (
        "Elétrica",
        "Fio 2,5 mm²",
        "m",
        "Condutor elétrico."
    ),

    (
        "Elétrica",
        "Fio 4 mm²",
        "m",
        "Condutor elétrico."
    ),

    (
        "Elétrica",
        "Fio 6 mm²",
        "m",
        "Condutor elétrico."
    ),

    (
        "Elétrica",
        "Cabo flexível 10 mm²",
        "m",
        "Cabo elétrico."
    ),

    (
        "Elétrica",
        "Eletroduto PVC 20 mm",
        "barra",
        "Eletroduto para instalações elétricas."
    ),

    (
        "Elétrica",
        "Eletroduto PVC 25 mm",
        "barra",
        "Eletroduto para instalações elétricas."
    ),

    (
        "Elétrica",
        "Caixa 4x2",
        "un",
        "Caixa para interruptores e tomadas."
    ),

    (
        "Elétrica",
        "Caixa 4x4",
        "un",
        "Caixa para instalações elétricas."
    ),

    (
        "Elétrica",
        "Tomada 10 A",
        "un",
        "Tomada elétrica."
    ),

    (
        "Elétrica",
        "Tomada 20 A",
        "un",
        "Tomada elétrica."
    ),

    (
        "Elétrica",
        "Interruptor simples",
        "un",
        "Interruptor elétrico."
    ),

    (
        "Elétrica",
        "Disjuntor monopolar",
        "un",
        "Disjuntor de proteção."
    ),

    (
        "Elétrica",
        "Disjuntor bipolar",
        "un",
        "Disjuntor de proteção."
    ),

    (
        "Elétrica",
        "Quadro de distribuição",
        "un",
        "Quadro para distribuição elétrica."
    ),

    (
        "Pisos e revestimentos",
        "Piso cerâmico",
        "m²",
        "Piso cerâmico para revestimento."
    ),

    (
        "Pisos e revestimentos",
        "Porcelanato",
        "m²",
        "Revestimento porcelanato."
    ),

    (
        "Pisos e revestimentos",
        "Azulejo",
        "m²",
        "Revestimento cerâmico para paredes."
    ),

    (
        "Pisos e revestimentos",
        "Rodapé cerâmico",
        "m",
        "Rodapé para acabamento."
    ),

    (
        "Pintura",
        "Tinta acrílica",
        "L",
        "Tinta para paredes e tetos."
    ),

    (
        "Pintura",
        "Tinta látex PVA",
        "L",
        "Tinta para ambientes internos."
    ),

    (
        "Pintura",
        "Selador acrílico",
        "L",
        "Selador para preparação de paredes."
    ),

    (
        "Pintura",
        "Massa corrida",
        "kg",
        "Massa para regularização interna."
    ),

    (
        "Pintura",
        "Massa acrílica",
        "kg",
        "Massa para regularização externa e interna."
    ),

    (
        "Pintura",
        "Fundo preparador",
        "L",
        "Fundo para preparação de superfícies."
    ),

    (
        "Fixação",
        "Parafuso para madeira",
        "un",
        "Parafuso para madeira."
    ),

    (
        "Fixação",
        "Parafuso para drywall",
        "un",
        "Parafuso para drywall."
    ),

    (
        "Fixação",
        "Bucha 6 mm",
        "un",
        "Bucha para fixação."
    ),

    (
        "Fixação",
        "Bucha 8 mm",
        "un",
        "Bucha para fixação."
    ),

    (
        "Fixação",
        "Bucha 10 mm",
        "un",
        "Bucha para fixação."
    ),

    (
        "Fixação",
        "Abraçadeira de nylon",
        "un",
        "Abraçadeira para organização e fixação."
    ),

    (
        "EPIs",
        "Capacete de segurança",
        "un",
        "Equipamento de proteção individual."
    ),

    (
        "EPIs",
        "Óculos de proteção",
        "un",
        "Equipamento de proteção individual."
    ),

    (
        "EPIs",
        "Luva de proteção",
        "par",
        "Equipamento de proteção individual."
    ),

    (
        "EPIs",
        "Protetor auricular",
        "par",
        "Equipamento de proteção individual."
    ),

    (
        "EPIs",
        "Botina de segurança",
        "par",
        "Equipamento de proteção individual."
    ),

    (
        "EPIs",
        "Máscara respiratória",
        "un",
        "Equipamento de proteção individual."
    ),
]


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


def normalizar_texto_catalogo(valor):

    valor = (valor or "").strip().casefold()

    return "".join(
        caractere
        for caractere in unicodedata.normalize(
            "NFKD",
            valor
        )
        if not unicodedata.combining(caractere)
    )


def dados_material_catalogo():

    return [
        {
            "categoria": categoria,
            "nome": nome,
            "unidade": unidade,
            "descricao": descricao,
        }
        for categoria, nome, unidade, descricao
        in MATERIAIS_CATALOGO
    ]


def material_catalogo_por_nome(nome):

    alvo = normalizar_texto_catalogo(
        nome
    )

    for (
        categoria,
        nome_catalogo,
        unidade,
        descricao
    ) in MATERIAIS_CATALOGO:

        if (
            normalizar_texto_catalogo(
                nome_catalogo
            )
            == alvo
        ):

            return {
                "categoria": categoria,
                "nome": nome_catalogo,
                "unidade": unidade,
                "descricao": descricao,
            }

    return None


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


def usuario_tem_acesso_obra(
    usuario,
    obra
):

    if not usuario or not obra:
        return False

    if usuario.funcao == "adm":
        return True

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


def obras_do_usuario(
    usuario=None
):

    usuario = usuario or current_user

    if (
        not usuario
        or not usuario.is_authenticated
    ):

        return []

    if usuario.funcao == "adm":

        return Obra.query.order_by(
            Obra.criado_em.desc()
        ).all()

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


def usuario_pode_gerenciar_obra(
    obra
):

    if not current_user.is_authenticated:
        return False

    if eh_administrador():
        return True

    if eh_administrador_empresa():

        return (
            current_user.empresa_id
            == obra.empresa_id
        )

    return False


def empresa_admin_obrigatorio(func):

    @wraps(func)
    def decorated_function(
        *args,
        **kwargs
    ):

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

        if not eh_gestor_empresa():

            flash(
                "Você não possui permissão para esta função.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        if (
            not eh_administrador()
            and current_user.empresa_id
        ):

            empresa = db.session.get(
                Empresa,
                current_user.empresa_id
            )

            if (
                not empresa
                or not empresa.ativo
            ):

                logout_user()

                flash(
                    "A empresa vinculada ao usuário está inativa.",
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


def login_obrigatorio(func):

    @wraps(func)
    def decorated_function(
        *args,
        **kwargs
    ):

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

        if eh_administrador():
            return func(
                *args,
                **kwargs
            )

        empresa = empresa_usuario_atual()

        if (
            not empresa
            or not empresa.ativo
        ):

            logout_user()

            flash(
                "A empresa vinculada ao usuário "
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


def admin_obrigatorio(func):

    @wraps(func)
    @login_obrigatorio
    def decorated_function(
        *args,
        **kwargs
    ):

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


class Usuario(
    UserMixin,
    db.Model
):

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

    def definir_senha(
        self,
        senha
    ):

        self.senha_hash = (
            generate_password_hash(
                senha
            )
        )

    def verificar_senha(
        self,
        senha
    ):

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

    tipo_recurso = db.Column(
        db.String(30),
        nullable=False,
        default="material"
    )

    recurso_nome = db.Column(
        db.String(200),
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
        "tipos_solicitacao": TIPOS_SOLICITACAO,
        "catalogo_materiais": dados_material_catalogo(),
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

        return redirect(
            url_for("dashboard")
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

        if not usuario.verificar_senha(
            senha
        ):

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
                "A empresa vinculada ao usuário "
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
            url_for("dashboard")
        )

    return render_template(
        "login.html"
    )


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
# DASHBOARD
# ============================================================

@app.route("/")
@login_obrigatorio
def dashboard():

    if eh_administrador():

        empresas_count = Empresa.query.count()

        obras_count = Obra.query.count()

        usuarios_count = Usuario.query.count()

        solicitacoes_pendentes = (
            Solicitacao.query
            .filter_by(
                status="pendente"
            )
            .count()
        )

        return render_template(
            "dashboard.html",
            empresas_count=empresas_count,
            obras_count=obras_count,
            usuarios_count=usuarios_count,
            solicitacoes_pendentes=(
                solicitacoes_pendentes
            ),
        )

    empresa = empresa_usuario_atual()

    obras_count = Obra.query.filter_by(
        empresa_id=empresa.id
    ).count()

    usuarios_count = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    solicitacoes_pendentes = (
        Solicitacao.query
        .join(
            Obra,
            Solicitacao.obra_id == Obra.id
        )
        .filter(
            Obra.empresa_id == empresa.id,
            Solicitacao.status == "pendente"
        )
        .count()
    )

    return render_template(
        "dashboard.html",
        empresa=empresa,
        obras_count=obras_count,
        usuarios_count=usuarios_count,
        solicitacoes_pendentes=(
            solicitacoes_pendentes
        ),
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

    total_usuarios = Usuario.query.count()

    total_obras = Obra.query.count()

    solicitacoes_pendentes = (
        Solicitacao.query
        .filter_by(
            status="pendente"
        )
        .count()
    )

    return render_template(
        "admin_dashboard.html",
        empresas=empresas,
        total_empresas=total_empresas,
        empresas_ativas=empresas_ativas,
        total_usuarios=total_usuarios,
        total_obras=total_obras,
        solicitacoes_pendentes=(
            solicitacoes_pendentes
        ),
    )


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
# EMPRESAS
# ============================================================

@app.route(
    "/admin/empresas/nova",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def nova_empresa():

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

            flash(
                "Empresa cadastrada com sucesso.",
                "success"
            )

            return redirect(
                url_for(
                    "empresa_detalhes",
                    empresa_id=empresa.id
                )
            )

        except IntegrityError:

            db.session.rollback()

            flash(
                "Já existe uma empresa com este CNPJ.",
                "danger"
            )

    return render_template(
        "empresa_form.html",
        empresa=None,
        titulo="Nova empresa"
    )


@app.route(
    "/admin/empresas/<int:empresa_id>"
)
@admin_obrigatorio
def empresa_detalhes(
    empresa_id
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

    usuarios = (
        Usuario.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Usuario.nome.asc()
        )
        .all()
    )

    obras = (
        Obra.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Obra.criado_em.desc()
        )
        .all()
    )

    return render_template(
        "empresa_detalhes.html",
        empresa=empresa,
        usuarios=usuarios,
        obras=obras,
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/editar",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def editar_empresa(
    empresa_id
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

    if request.method == "POST":

        empresa.razao_social = (
            request.form.get("razao_social")
            or ""
        ).strip()

        empresa.nome_fantasia = (
            request.form.get("nome_fantasia")
            or ""
        ).strip()

        empresa.cnpj = (
            normalizar_cnpj(
                request.form.get("cnpj")
            )
            or None
        )

        empresa.telefone = (
            request.form.get("telefone")
            or ""
        ).strip()

        empresa.email = (
            request.form.get("email")
            or ""
        ).strip()

        empresa.endereco = (
            request.form.get("endereco")
            or ""
        ).strip()

        try:

            db.session.commit()

            flash(
                "Empresa atualizada com sucesso.",
                "success"
            )

            return redirect(
                url_for(
                    "empresa_detalhes",
                    empresa_id=empresa.id
                )
            )

        except IntegrityError:

            db.session.rollback()

            flash(
                "Não foi possível atualizar. "
                "Verifique se o CNPJ já está cadastrado.",
                "danger"
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
def alternar_status_empresa(
    empresa_id
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

    empresa.ativo = not empresa.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status da empresa."
        )

        flash(
            "Não foi possível alterar o status da empresa.",
            "danger"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    flash(
        "Status da empresa atualizado.",
        "success"
    )

    return redirect(
        url_for(
            "empresa_detalhes",
            empresa_id=empresa.id
        )
    )


@app.route(
    "/admin/empresas/<int:empresa_id>/excluir",
    methods=["POST"]
)
@admin_obrigatorio
def excluir_empresa(
    empresa_id
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

    if empresa.usuarios:

        flash(
            "Não é possível excluir uma empresa "
            "que possui usuários cadastrados. "
            "Desative a empresa em vez de excluí-la.",
            "warning"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    if empresa.obras:

        flash(
            "Não é possível excluir uma empresa "
            "que possui obras cadastradas.",
            "warning"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    db.session.delete(
        empresa
    )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao excluir empresa."
        )

        flash(
            "Não foi possível excluir a empresa.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    flash(
        "Empresa excluída.",
        "success"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# USUÁRIOS / FUNCIONÁRIOS
# ============================================================

@app.route(
    "/admin/empresas/<int:empresa_id>/usuarios/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def novo_usuario_empresa(
    empresa_id
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
            url_for(
                "admin_dashboard"
                if eh_administrador()
                else "funcionarios"
            )
        )

    if (
        not eh_administrador()
        and (
            not eh_administrador_empresa()
            or current_user.empresa_id != empresa.id
        )
    ):

        flash(
            "Você não possui acesso a esta empresa.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

    obras = (
        Obra.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Obra.nome.asc()
        )
        .all()
    )

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

        if funcao in (
            "adm",
            "administrador_empresa",
            "admin_empresa",
        ):

            if not eh_administrador():

                funcao = "funcionario"

        if (
            not nome
            or not usuario_login
            or not senha
        ):

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


@app.route(
    "/admin/empresas/<int:empresa_id>/administrador/novo",
    methods=["GET", "POST"]
)
@admin_obrigatorio
def novo_administrador_empresa(
    empresa_id
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

    if not empresa.ativo:

        flash(
            "Ative a empresa antes de cadastrar o administrador.",
            "warning"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    administrador_existente = (
        Usuario.query
        .filter(
            Usuario.empresa_id == empresa.id,
            Usuario.funcao.in_(
                (
                    "administrador_empresa",
                    "admin_empresa",
                )
            )
        )
        .first()
    )

    if (
        request.method == "GET"
        and administrador_existente
    ):

        flash(
            "Esta empresa já possui um administrador. "
            "Edite o administrador existente ou desative-o "
            "antes de criar outro.",
            "info"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

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

        if (
            not nome
            or not usuario_login
            or not senha
        ):

            flash(
                "Nome, usuário e senha do administrador "
                "são obrigatórios.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=[],
                titulo="Novo administrador da empresa",
                modo_administrador=True,
            )

        outro_usuario = Usuario.query.filter_by(
            usuario=usuario_login
        ).first()

        if outro_usuario:

            flash(
                "Este nome de usuário já está sendo utilizado.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=[],
                titulo="Novo administrador da empresa",
                modo_administrador=True,
            )

        if administrador_existente:

            flash(
                "Esta empresa já possui um administrador.",
                "warning"
            )

            return redirect(
                url_for(
                    "empresa_detalhes",
                    empresa_id=empresa.id
                )
            )

        administrador = Usuario(
            nome=nome,
            usuario=usuario_login,
            funcao="administrador_empresa",
            ativo=True,
            empresa_id=empresa.id,
        )

        administrador.definir_senha(
            senha
        )

        db.session.add(
            administrador
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao cadastrar administrador da empresa."
            )

            flash(
                "Não foi possível cadastrar o administrador "
                "da empresa.",
                "danger"
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=empresa,
                obras=[],
                titulo="Novo administrador da empresa",
                modo_administrador=True,
            )

        flash(
            "Administrador da empreiteira cadastrado com sucesso.",
            "success"
        )

        return redirect(
            url_for(
                "empresa_detalhes",
                empresa_id=empresa.id
            )
        )

    return render_template(
        "funcionario_form.html",
        funcionario=None,
        empresa=empresa,
        obras=[],
        titulo="Novo administrador da empresa",
        modo_administrador=True,
    )


@app.route(
    "/funcionarios",
    methods=["GET"]
)
@empresa_admin_obrigatorio
def funcionarios():

    if eh_administrador():

        empresa_id = request.args.get(
            "empresa_id",
            type=int
        )

        if empresa_id:

            empresa = db.session.get(
                Empresa,
                empresa_id
            )

            if empresa:

                usuarios = (
                    Usuario.query
                    .filter_by(
                        empresa_id=empresa.id
                    )
                    .order_by(
                        Usuario.nome.asc()
                    )
                    .all()
                )

                obras = (
                    Obra.query
                    .filter_by(
                        empresa_id=empresa.id
                    )
                    .order_by(
                        Obra.nome.asc()
                    )
                    .all()
                )

                return render_template(
                    "funcionarios.html",
                    funcionarios=usuarios,
                    obras=obras,
                    empresa=empresa,
                )

        usuarios = (
            Usuario.query
            .filter(
                Usuario.funcao != "adm"
            )
            .order_by(
                Usuario.nome.asc()
            )
            .all()
        )

        return render_template(
            "funcionarios.html",
            funcionarios=usuarios,
            obras=[],
            empresa=None,
        )

    empresa = empresa_usuario_atual()

    usuarios = (
        Usuario.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Usuario.nome.asc()
        )
        .all()
    )

    obras = (
        Obra.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Obra.nome.asc()
        )
        .all()
    )

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

    if eh_administrador():

        empresa_id = request.args.get(
            "empresa_id",
            type=int
        )

        if not empresa_id:

            empresas = (
                Empresa.query
                .filter_by(
                    ativo=True
                )
                .order_by(
                    Empresa.nome_fantasia.asc()
                )
                .all()
            )

            return render_template(
                "funcionario_form.html",
                funcionario=None,
                empresa=None,
                empresas=empresas,
                obras=[],
                titulo="Novo funcionário"
            )

        empresa = db.session.get(
            Empresa,
            empresa_id
        )

    else:

        empresa = empresa_usuario_atual()

    if not empresa:

        flash(
            "Empresa não encontrada.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
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
def editar_funcionario(
    usuario_id
):

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
        funcionario.funcao
        in (
            "administrador_empresa",
            "admin_empresa",
        )
        and not eh_administrador()
    ):

        flash(
            "O administrador da empresa é gerenciado "
            "pelo ADM geral.",
            "warning"
        )

        return redirect(
            url_for("funcionarios")
        )

    if (
        not eh_administrador()
        and funcionario.empresa_id
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

    obras = (
        Obra.query
        .filter_by(
            empresa_id=empresa.id
        )
        .order_by(
            Obra.nome.asc()
        )
        .all()
    )

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

        outro_usuario = (
            Usuario.query
            .filter(
                Usuario.usuario == usuario_login,
                Usuario.id != funcionario.id
            )
            .first()
        )

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
def alternar_status_funcionario(
    usuario_id
):

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
        funcionario.funcao
        in (
            "administrador_empresa",
            "admin_empresa",
        )
        and not eh_administrador()
    ):

        flash(
            "O administrador da empresa é gerenciado "
            "pelo ADM geral.",
            "warning"
        )

        return redirect(
            url_for("funcionarios")
        )

    if (
        not eh_administrador()
        and funcionario.empresa_id
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

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status do funcionário."
        )

        flash(
            "Não foi possível alterar o status.",
            "danger"
        )

        return redirect(
            url_for("funcionarios")
        )

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
@login_obrigatorio
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

    if eh_administrador():

        empresas = (
            Empresa.query
            .filter_by(
                ativo=True
            )
            .order_by(
                Empresa.nome_fantasia.asc()
            )
            .all()
        )

    else:

        empresas = [
            empresa_usuario_atual()
        ]

    if request.method == "POST":

        empresa_id = request.form.get(
            "empresa_id",
            type=int
        )

        if not eh_administrador():

            empresa_id = current_user.empresa_id

        empresa = db.session.get(
            Empresa,
            empresa_id
        )

        if (
            not empresa
            or not empresa.ativo
        ):

            flash(
                "Empresa inválida ou inativa.",
                "danger"
            )

            return redirect(
                url_for("nova_obra")
            )

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

                pass

        if previsao_raw:

            try:

                previsao_termino = datetime.strptime(
                    previsao_raw,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                pass

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
@login_obrigatorio
def obra_detalhes(
    obra_id
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

    vinculos = (
        UsuarioObra.query
        .filter_by(
            obra_id=obra.id
        )
        .all()
    )

    solicitacoes = (
        Solicitacao.query
        .filter_by(
            obra_id=obra.id
        )
        .order_by(
            Solicitacao.criado_em.desc()
        )
        .all()
    )

    equipe_acesso = None

    for vinculo in vinculos:

        if (
            vinculo.usuario
            and vinculo.usuario.funcao
            == "equipe_obra"
        ):

            equipe_acesso = (
                vinculo.usuario
            )

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
def editar_obra(
    obra_id
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

    if eh_administrador():

        empresas = (
            Empresa.query
            .filter_by(
                ativo=True
            )
            .order_by(
                Empresa.nome_fantasia.asc()
            )
            .all()
        )

    else:

        empresas = [
            empresa_usuario_atual()
        ]

    if request.method == "POST":

        if not eh_administrador():

            empresa_id = current_user.empresa_id

        else:

            empresa_id = request.form.get(
                "empresa_id",
                type=int
            )

        empresa = db.session.get(
            Empresa,
            empresa_id
        )

        if (
            not empresa
            or not empresa.ativo
        ):

            flash(
                "Empresa inválida ou inativa.",
                "danger"
            )

            return redirect(
                url_for(
                    "editar_obra",
                    obra_id=obra.id
                )
            )

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

        obra.empresa_id = empresa.id

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


@app.route(
    "/obras/<int:obra_id>/finalizar",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def finalizar_obra(
    obra_id
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

    if not usuario_pode_gerenciar_obra(
        obra
    ):

        flash(
            "Você não possui permissão para finalizar esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if obra.status == "concluida":

        flash(
            "Esta obra já está finalizada.",
            "info"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    obra.status = "concluida"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao finalizar obra."
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

    flash(
        "Obra finalizada com sucesso.",
        "success"
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
def excluir_obra(
    obra_id
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

    if not usuario_pode_gerenciar_obra(
        obra
    ):

        flash(
            "Você não possui permissão para excluir esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    if (
        Solicitacao.query
        .filter_by(
            obra_id=obra.id
        )
        .first()
    ):

        flash(
            "Esta obra possui solicitações registradas. "
            "Finalize a obra em vez de excluí-la.",
            "warning"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    UsuarioObra.query.filter_by(
        obra_id=obra.id
    ).delete(
        synchronize_session=False
    )

    db.session.delete(
        obra
    )

    try:

        db.session.commit()

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
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    flash(
        "Obra excluída com sucesso.",
        "success"
    )

    return redirect(
        url_for("obras")
    )


# ============================================================
# ACESSO COMPARTILHADO PEDREIRO / AJUDANTE
# ============================================================

@app.route(
    "/obras/<int:obra_id>/equipe-acesso",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def salvar_acesso_equipe(
    obra_id
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

    if not usuario_pode_gerenciar_obra(
        obra
    ):

        flash(
            "Você não possui permissão para esta obra.",
            "danger"
        )

        return redirect(
            url_for("obras")
        )

    nome = (
        request.form.get("nome")
        or f"Equipe - {obra.nome}"
    ).strip()

    usuario_login = normalizar_usuario(
        request.form.get("usuario")
    )

    senha = request.form.get(
        "senha",
        ""
    )

    if not usuario_login:

        flash(
            "Informe o usuário da equipe.",
            "danger"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    equipe_existente = None

    vinculos = (
        UsuarioObra.query
        .filter_by(
            obra_id=obra.id
        )
        .all()
    )

    for vinculo in vinculos:

        if (
            vinculo.usuario
            and vinculo.usuario.funcao
            == "equipe_obra"
        ):

            equipe_existente = (
                vinculo.usuario
            )

            break

    usuario_com_mesmo_login = (
        Usuario.query
        .filter_by(
            usuario=usuario_login
        )
        .first()
    )

    if (
        usuario_com_mesmo_login
        and (
            not equipe_existente
            or usuario_com_mesmo_login.id
            != equipe_existente.id
        )
    ):

        flash(
            "Este nome de usuário já está sendo utilizado.",
            "danger"
        )

        return redirect(
            url_for(
                "obra_detalhes",
                obra_id=obra.id
            )
        )

    if equipe_existente:

        equipe_existente.nome = nome

        equipe_existente.usuario = usuario_login

        if senha.strip():

            equipe_existente.definir_senha(
                senha
            )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao atualizar acesso da equipe."
            )

            flash(
                "Não foi possível atualizar o acesso da equipe.",
                "danger"
            )

            return redirect(
                url_for(
                    "obra_detalhes",
                    obra_id=obra.id
                )
            )

        flash(
            "Acesso da equipe atualizado.",
            "success"
        )

    else:

        if not senha.strip():

            flash(
                "Informe uma senha para criar o acesso da equipe.",
                "danger"
            )

            return redirect(
                url_for(
                    "obra_detalhes",
                    obra_id=obra.id
                )
            )

        novo_usuario = Usuario(
            nome=nome,
            usuario=usuario_login,
            funcao="equipe_obra",
            ativo=True,
            empresa_id=obra.empresa_id,
        )

        novo_usuario.definir_senha(
            senha
        )

        db.session.add(
            novo_usuario
        )

        try:

            db.session.flush()

            db.session.add(
                UsuarioObra(
                    usuario_id=novo_usuario.id,
                    obra_id=obra.id,
                    funcao_na_obra="equipe_obra",
                )
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao criar acesso da equipe"
            )

            flash(
                "Não foi possível criar o acesso da equipe.",
                "danger"
            )

            return redirect(
                url_for(
                    "obra_detalhes",
                    obra_id=obra.id
                )
            )

        flash(
            "Acesso compartilhado da equipe criado.",
            "success"
        )

    return redirect(
        url_for(
            "obra_detalhes",
            obra_id=obra.id
        )
    )


# ============================================================
# MATERIAIS
# ============================================================

@app.route("/materiais")
@login_obrigatorio
def materiais():

    materiais_lista = (
        Material.query
        .filter_by(
            ativo=True
        )
        .order_by(
            Material.categoria.asc(),
            Material.nome.asc()
        )
        .all()
    )

    return render_template(
        "materiais.html",
        materiais=materiais_lista
    )


@app.route(
    "/materiais/novo",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
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

        item_catalogo = material_catalogo_por_nome(
            nome
        )

        if item_catalogo:

            categoria = item_catalogo["categoria"]

        descricao = (
            request.form.get("descricao")
            or ""
        ).strip()

        if (
            item_catalogo
            and not descricao
        ):

            descricao = item_catalogo[
                "descricao"
            ]

        unidade = (
            request.form.get("unidade")
            or ""
        ).strip()

        if (
            item_catalogo
            and not unidade
        ):

            unidade = item_catalogo[
                "unidade"
            ]

        if not unidade:
            unidade = "un"

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

            estoque_minimo = 0

            estoque_atual = 0

        estoque_minimo = max(
            0,
            estoque_minimo
        )

        estoque_atual = max(
            0,
            estoque_atual
        )

        if not categoria or not nome:

            flash(
                "Categoria e nome são obrigatórios.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=None,
                titulo="Novo material",
                catalogo_materiais=(
                    dados_material_catalogo()
                ),
            )

        material = Material(
            categoria=categoria,
            nome=nome,
            descricao=descricao,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual,
            ativo=True,
        )

        db.session.add(
            material
        )

        try:

            db.session.commit()

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
                titulo="Novo material",
                catalogo_materiais=(
                    dados_material_catalogo()
                ),
            )

        flash(
            "Material cadastrado com sucesso.",
            "success"
        )

        return redirect(
            url_for("materiais")
        )

    return render_template(
        "material_form.html",
        material=None,
        titulo="Novo material",
        catalogo_materiais=(
            dados_material_catalogo()
        ),
    )


@app.route(
    "/materiais/<int:material_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_material(
    material_id
):

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

    if request.method == "POST":

        nome = (
            request.form.get("nome")
            or ""
        ).strip()

        categoria = (
            request.form.get("categoria")
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

        item_catalogo = material_catalogo_por_nome(
            nome
        )

        if item_catalogo:

            categoria = item_catalogo[
                "categoria"
            ]

            if not descricao:

                descricao = item_catalogo[
                    "descricao"
                ]

            if not unidade:

                unidade = item_catalogo[
                    "unidade"
                ]

        if not unidade:
            unidade = "un"

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
                "Informe valores numéricos válidos para o estoque.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=material,
                titulo="Editar material",
                catalogo_materiais=(
                    dados_material_catalogo()
                ),
            )

        if not nome or not categoria:

            flash(
                "Nome e categoria são obrigatórios.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=material,
                titulo="Editar material",
                catalogo_materiais=(
                    dados_material_catalogo()
                ),
            )

        material.nome = nome

        material.categoria = categoria

        material.descricao = descricao

        material.unidade = unidade

        material.estoque_minimo = max(
            0,
            estoque_minimo
        )

        material.estoque_atual = max(
            0,
            estoque_atual
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            logging.exception(
                "Erro ao editar material."
            )

            flash(
                "Não foi possível atualizar o material.",
                "danger"
            )

            return render_template(
                "material_form.html",
                material=material,
                titulo="Editar material",
                catalogo_materiais=(
                    dados_material_catalogo()
                ),
            )

        flash(
            "Material atualizado com sucesso.",
            "success"
        )

        return redirect(
            url_for("materiais")
        )

    return render_template(
        "material_form.html",
        material=material,
        titulo="Editar material",
        catalogo_materiais=(
            dados_material_catalogo()
        ),
    )


@app.route(
    "/materiais/<int:material_id>/alternar-status",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def alternar_status_material(
    material_id
):

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

    material.ativo = not material.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status do material."
        )

        flash(
            "Não foi possível alterar o status do material.",
            "danger"
        )

        return redirect(
            url_for("materiais")
        )

    flash(
        "Status do material atualizado.",
        "success"
    )

    return redirect(
        url_for("materiais")
    )


# ============================================================
# FERRAMENTAS
# ============================================================

@app.route("/ferramentas")
@login_obrigatorio
def ferramentas():

    ferramentas_lista = (
        Ferramenta.query
        .filter_by(
            ativo=True
        )
        .order_by(
            Ferramenta.categoria.asc(),
            Ferramenta.nome.asc()
        )
        .all()
    )

    return render_template(
        "ferramentas.html",
        ferramentas=ferramentas_lista
    )


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

            estoque_minimo = 0

            estoque_atual = 0

        estoque_minimo = max(
            0,
            estoque_minimo
        )

        estoque_atual = max(
            0,
            estoque_atual
        )

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
            categoria=categoria,
            nome=nome,
            descricao=descricao,
            unidade=unidade,
            estoque_minimo=estoque_minimo,
            estoque_atual=estoque_atual,
            ativo=True,
        )

        db.session.add(
            ferramenta
        )

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


@app.route(
    "/ferramentas/<int:ferramenta_id>/editar",
    methods=["GET", "POST"]
)
@empresa_admin_obrigatorio
def editar_ferramenta(
    ferramenta_id
):

    ferramenta = obter_ferramenta(
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
                "Informe valores numéricos válidos para o estoque.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta",
            )

        if not nome or not categoria:

            flash(
                "Nome e categoria são obrigatórios.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta",
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
                "Erro ao editar ferramenta."
            )

            flash(
                "Não foi possível atualizar a ferramenta.",
                "danger"
            )

            return render_template(
                "ferramenta_form.html",
                ferramenta=ferramenta,
                titulo="Editar ferramenta",
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
        titulo="Editar ferramenta",
    )


@app.route(
    "/ferramentas/<int:ferramenta_id>/alternar-status",
    methods=["POST"]
)
@empresa_admin_obrigatorio
def alternar_status_ferramenta(
    ferramenta_id
):

    ferramenta = obter_ferramenta(
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

    ferramenta.ativo = not ferramenta.ativo

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao alterar status da ferramenta."
        )

        flash(
            "Não foi possível alterar o status da ferramenta.",
            "danger"
        )

        return redirect(
            url_for("ferramentas")
        )

    flash(
        "Status da ferramenta atualizado.",
        "success"
    )

    return redirect(
        url_for("ferramentas")
    )


# ============================================================
# SOLICITAÇÕES
# ============================================================

@app.route("/solicitacoes")
@login_obrigatorio
def solicitacoes():

    if eh_administrador():

        lista = (
            Solicitacao.query
            .order_by(
                Solicitacao.criado_em.desc()
            )
            .all()
        )

    elif eh_administrador_empresa():

        lista = (
            Solicitacao.query
            .join(
                Obra,
                Solicitacao.obra_id == Obra.id
            )
            .filter(
                Obra.empresa_id
                == current_user.empresa_id
            )
            .order_by(
                Solicitacao.criado_em.desc()
            )
            .all()
        )

    else:

        obra_ids = [
            obra.id
            for obra in obras_do_usuario()
        ]

        if not obra_ids:

            lista = []

        else:

            lista = (
                Solicitacao.query
                .filter(
                    Solicitacao.obra_id.in_(
                        obra_ids
                    )
                )
                .order_by(
                    Solicitacao.criado_em.desc()
                )
                .all()
            )

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

    obras_disponiveis = obras_do_usuario()

    materiais_lista = (
        Material.query
        .filter_by(
            ativo=True
        )
        .order_by(
            Material.categoria.asc(),
            Material.nome.asc()
        )
        .all()
    )

    ferramentas_lista = (
        Ferramenta.query
        .filter_by(
            ativo=True
        )
        .order_by(
            Ferramenta.categoria.asc(),
            Ferramenta.nome.asc()
        )
        .all()
    )

    if not obras_disponiveis:

        flash(
            "Você ainda não possui nenhuma obra vinculada.",
            "warning"
        )

        return redirect(
            url_for("obras")
        )

    if request.method == "POST":

        obra_id = request.form.get(
            "obra_id",
            type=int
        )

        tipo = (
            request.form.get("tipo")
            or "material"
        ).strip().lower()

        recurso_nome = (
            request.form.get("recurso_nome")
            or ""
        ).strip()

        recurso_id = request.form.get(
            "recurso_id",
            type=int
        )

        quantidade_raw = (
            request.form.get("quantidade")
            or "0"
        )

        observacao = (
            request.form.get("observacao")
            or ""
        ).strip()

        obra = db.session.get(
            Obra,
            obra_id
        )

        if not obra:

            flash(
                "Obra inválida.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
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
                url_for("nova_solicitacao")
            )

        if obra.status == "concluida":

            flash(
                "Esta obra já foi finalizada e "
                "não aceita novas solicitações.",
                "warning"
            )

            return redirect(
                url_for(
                    "obra_detalhes",
                    obra_id=obra.id
                )
            )

        try:

            quantidade = float(
                quantidade_raw
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

            return render_template(
                "solicitacao_form.html",
                obras=obras_disponiveis,
                materiais=materiais_lista,
                ferramentas=ferramentas_lista,
            )

        if tipo not in (
            "material",
            "ferramenta",
            "outro",
        ):

            flash(
                "Tipo de recurso inválido.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if (
            tipo != "outro"
            and not recurso_id
        ):

            flash(
                "Selecione um material ou ferramenta.",
                "danger"
            )

            return redirect(
                url_for("nova_solicitacao")
            )

        if (
            tipo == "outro"
            and not recurso_nome
        ):

            flash(
                "Informe o nome do item ou compra solicitada.",
                "danger"
            )

            return render_template(
                "solicitacao_form.html",
                obras=obras_disponiveis,
                materiais=materiais_lista,
                ferramentas=ferramentas_lista,
            )

        nova = Solicitacao(
            obra_id=obra.id,
            usuario_id=current_user.id,
            quantidade=quantidade,
            observacao=observacao,
            status="pendente",
            tipo_recurso=tipo,
            recurso_nome=(
                recurso_nome
                or None
            ),
        )

        if tipo == "material":

            material = obter_material(
                recurso_id
            )

            if (
                not material
                or not material.ativo
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

        elif tipo == "ferramenta":

            ferramenta = obter_ferramenta(
                recurso_id
            )

            if (
                not ferramenta
                or not ferramenta.ativo
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

        else:

            nova.material_id = None

            nova.ferramenta_id = None

        db.session.add(
            nova
        )

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
            "Solicitação enviada para aprovação do ADM.",
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
    )


# ============================================================
# CONFIRMAÇÃO DA SOLICITAÇÃO PELO ADM
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

    # Em PostgreSQL, bloqueia a solicitação durante a confirmação.
    # Isso evita duas confirmações simultâneas adicionarem
    # o estoque duas vezes.
    if solicitacao:

        try:

            solicitacao = (
                db.session.query(
                    Solicitacao
                )
                .filter_by(
                    id=solicitacao_id
                )
                .with_for_update()
                .first()
            )

        except Exception:

            db.session.rollback()

            logging.exception(
                "Não foi possível bloquear a solicitação "
                "para confirmação."
            )

            flash(
                "Não foi possível processar a confirmação agora.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
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

    if not usuario_pode_gerenciar_obra(
        obra
    ):

        flash(
            "Você não possui permissão para confirmar "
            "solicitações desta obra.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

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

    tipo_recurso = (
        solicitacao.tipo_recurso
        or (
            "material"
            if solicitacao.material_id
            else "ferramenta"
            if solicitacao.ferramenta_id
            else "outro"
        )
    )

    if (
        tipo_recurso == "material"
        and solicitacao.material_id
    ):

        material = obter_material(
            solicitacao.material_id
        )

        if not material:

            flash(
                "O material solicitado não foi encontrado.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        material.estoque_atual = (
            float(
                material.estoque_atual
                or 0
            )
            + float(
                solicitacao.quantidade
                or 0
            )
        )

    elif (
        tipo_recurso == "ferramenta"
        and solicitacao.ferramenta_id
    ):

        ferramenta = obter_ferramenta(
            solicitacao.ferramenta_id
        )

        if not ferramenta:

            flash(
                "A ferramenta solicitada não foi encontrada.",
                "danger"
            )

            return redirect(
                url_for("solicitacoes")
            )

        ferramenta.estoque_atual = (
            float(
                ferramenta.estoque_atual
                or 0
            )
            + float(
                solicitacao.quantidade
                or 0
            )
        )

    elif tipo_recurso == "outro":

        # Solicitações genéricas não alteram estoque automaticamente.
        # A confirmação apenas registra a compra.
        pass

    else:

        flash(
            "A solicitação possui um tipo de recurso inválido.",
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
            "Não foi possível confirmar a solicitação.",
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
# MARCAR COMO COMPRADO
# ============================================================

@app.route(
    "/solicitacoes/<int:solicitacao_id>/comprado",
    methods=["POST"]
)
@empresa_admin_obrigatorio
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
        or not usuario_pode_gerenciar_obra(
            obra
        )
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

    solicitacao.status = "comprado"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao marcar solicitação como comprada."
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
        "Agora o ADM pode confirmar a entrada no estoque.",
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
        or not usuario_pode_gerenciar_obra(
            obra
        )
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
            "Uma solicitação confirmada não pode ser cancelada.",
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
            "Erro ao cancelar solicitação."
        )

        flash(
            "Não foi possível cancelar a solicitação.",
            "danger"
        )

        return redirect(
            url_for("solicitacoes")
        )

    flash(
        "Solicitação cancelada.",
        "success"
    )

    return redirect(
        url_for("solicitacoes")
    )


# ============================================================
# MIGRAÇÃO ROBUSTA DO BANCO
# ============================================================

def coluna_existe(
    nome_tabela,
    nome_coluna
):

    inspector = inspect(
        db.engine
    )

    tabelas = inspector.get_table_names()

    if nome_tabela not in tabelas:
        return False

    colunas = inspector.get_columns(
        nome_tabela
    )

    return any(
        coluna["name"] == nome_coluna
        for coluna in colunas
    )


def tipo_sql_datetime():

    """
    PostgreSQL não utiliza DATETIME.
    SQLite aceita DATETIME.
    """

    dialect = db.engine.dialect.name

    if dialect == "postgresql":

        return "TIMESTAMP"

    return "DATETIME"


def adicionar_coluna_se_nao_existir(
    tabela,
    coluna,
    tipo_sql
):

    if coluna_existe(
        tabela,
        coluna
    ):

        logging.info(
            "Coluna já existe: %s.%s",
            tabela,
            coluna
        )

        return True

    try:

        comando = (
            f'ALTER TABLE "{tabela}" '
            f'ADD COLUMN "{coluna}" {tipo_sql}'
        )

        logging.info(
            "Executando migração: %s",
            comando
        )

        db.session.execute(
            text(comando)
        )

        db.session.commit()

        logging.info(
            "Coluna adicionada com sucesso: %s.%s",
            tabela,
            coluna
        )

        return True

    except Exception as erro:

        db.session.rollback()

        logging.exception(
            "Não foi possível adicionar coluna %s.%s",
            tabela,
            coluna
        )

        raise erro


def migrar_banco():

    """
    db.create_all() não altera tabelas existentes.

    Portanto, esta função verifica as tabelas existentes
    e adiciona somente colunas que estiverem faltando.

    Nenhuma informação existente é apagada.
    """

    logging.info(
        "Iniciando verificação/migração do banco..."
    )

    datetime_type = tipo_sql_datetime()

    # ========================================================
    # EMPRESAS
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "empresas",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # USUÁRIOS
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "usuarios",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # OBRAS
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "obras",
        "cliente",
        "VARCHAR(200)"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "endereco",
        "VARCHAR(300)"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "responsavel",
        "VARCHAR(150)"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "data_inicio",
        "DATE"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "previsao_termino",
        "DATE"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "status",
        "VARCHAR(50)"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "observacoes",
        "TEXT"
    )

    adicionar_coluna_se_nao_existir(
        "obras",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # USUÁRIO X OBRA
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "usuario_obras",
        "funcao_na_obra",
        "VARCHAR(80)"
    )

    adicionar_coluna_se_nao_existir(
        "usuario_obras",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # MATERIAIS
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "materiais",
        "categoria",
        "VARCHAR(120)"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "descricao",
        "TEXT"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "unidade",
        "VARCHAR(30)"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "estoque_minimo",
        "DOUBLE PRECISION"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "estoque_atual",
        "DOUBLE PRECISION"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "ativo",
        "BOOLEAN"
    )

    adicionar_coluna_se_nao_existir(
        "materiais",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # FERRAMENTAS
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "categoria",
        "VARCHAR(120)"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "descricao",
        "TEXT"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "unidade",
        "VARCHAR(30)"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "estoque_minimo",
        "DOUBLE PRECISION"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "estoque_atual",
        "DOUBLE PRECISION"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "ativo",
        "BOOLEAN"
    )

    adicionar_coluna_se_nao_existir(
        "ferramentas",
        "criado_em",
        datetime_type
    )

    # ========================================================
    # SOLICITAÇÕES
    # ========================================================

    adicionar_coluna_se_nao_existir(
        "solicitacoes",
        "ferramenta_id",
        "INTEGER"
    )

    adicionar_coluna_se_nao_existir(
        "solicitacoes",
        "confirmado_por_id",
        "INTEGER"
    )

    adicionar_coluna_se_nao_existir(
        "solicitacoes",
        "confirmado_em",
        datetime_type
    )

    adicionar_coluna_se_nao_existir(
        "solicitacoes",
        "tipo_recurso",
        "VARCHAR(30)"
    )

    adicionar_coluna_se_nao_existir(
        "solicitacoes",
        "recurso_nome",
        "VARCHAR(200)"
    )

    logging.info(
        "Verificação/migração do banco concluída."
    )


# ============================================================
# CATÁLOGO INICIAL DE FERRAMENTAS
# ============================================================

FERRAMENTAS_INICIAIS = [

    # MEDIÇÃO

    (
        "Medição",
        "Trena 5 metros",
        "Trena profissional de 5 metros",
        "un"
    ),

    (
        "Medição",
        "Trena 10 metros",
        "Trena profissional de 10 metros",
        "un"
    ),

    (
        "Medição",
        "Nível de bolha",
        "Nível manual para conferência",
        "un"
    ),

    (
        "Medição",
        "Nível a laser",
        "Nível a laser para alinhamento e nivelamento",
        "un"
    ),

    (
        "Medição",
        "Esquadro",
        "Esquadro para construção",
        "un"
    ),

    (
        "Medição",
        "Prumo",
        "Prumo de face para conferência vertical",
        "un"
    ),

    (
        "Medição",
        "Linha de pedreiro",
        "Linha para alinhamento de paredes",
        "un"
    ),

    (
        "Medição",
        "Mangueira de nível",
        "Mangueira transparente para nivelamento",
        "un"
    ),

    # ALVENARIA

    (
        "Alvenaria",
        "Colher de pedreiro",
        "Colher para aplicação de argamassa",
        "un"
    ),

    (
        "Alvenaria",
        "Desempenadeira lisa",
        "Desempenadeira para acabamento",
        "un"
    ),

    (
        "Alvenaria",
        "Desempenadeira dentada",
        "Desempenadeira para aplicação de argamassa",
        "un"
    ),

    (
        "Alvenaria",
        "Espátula",
        "Espátula para aplicação e acabamento",
        "un"
    ),

    (
        "Alvenaria",
        "Talhadeira",
        "Talhadeira para trabalhos em alvenaria",
        "un"
    ),

    (
        "Alvenaria",
        "Ponteiro",
        "Ponteiro para quebra e perfuração",
        "un"
    ),

    (
        "Alvenaria",
        "Marreta",
        "Marreta para demolição e alvenaria",
        "un"
    ),

    (
        "Alvenaria",
        "Martelo de pedreiro",
        "Martelo para trabalhos de alvenaria",
        "un"
    ),

    (
        "Alvenaria",
        "Régua de alumínio",
        "Régua para regularização",
        "un"
    ),

    # FERRAMENTAS MANUAIS

    (
        "Ferramentas manuais",
        "Serrote",
        "Serrote para cortes em madeira",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Arco de serra",
        "Arco manual para cortes",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Formão",
        "Formão para madeira",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Lima",
        "Lima para acabamento",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Alicate universal",
        "Alicate para serviços gerais",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Alicate de corte",
        "Alicate para cortes",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Chave de fenda",
        "Chave de fenda para serviços gerais",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Chave Phillips",
        "Chave Phillips",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Chave inglesa",
        "Chave ajustável",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Chave grifo",
        "Chave para tubulações",
        "un"
    ),

    (
        "Ferramentas manuais",
        "Torquês",
        "Torquês para corte e dobra",
        "un"
    ),

    # SERVIÇO PESADO

    (
        "Serviço pesado",
        "Pá de bico",
        "Pá para escavação",
        "un"
    ),

    (
        "Serviço pesado",
        "Pá quadrada",
        "Pá para movimentação de materiais",
        "un"
    ),

    (
        "Serviço pesado",
        "Enxada",
        "Enxada para escavação e limpeza",
        "un"
    ),

    (
        "Serviço pesado",
        "Picareta",
        "Picareta para escavação",
        "un"
    ),

    (
        "Serviço pesado",
        "Cavadeira",
        "Cavadeira manual",
        "un"
    ),

    (
        "Serviço pesado",
        "Carrinho de mão",
        "Carrinho para transporte de materiais",
        "un"
    ),

    (
        "Serviço pesado",
        "Balde de obra",
        "Balde para transporte de materiais",
        "un"
    ),

    (
        "Serviço pesado",
        "Peneira de areia",
        "Peneira para preparação de agregados",
        "un"
    ),

    # FERRAMENTAS ELÉTRICAS

    (
        "Ferramentas elétricas",
        "Furadeira",
        "Furadeira elétrica profissional",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Parafusadeira",
        "Parafusadeira elétrica",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Martelete",
        "Martelete para perfuração e demolição",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Esmerilhadeira",
        "Esmerilhadeira angular",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Serra circular",
        "Serra circular para madeira",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Serra mármore",
        "Serra para cortes em materiais de construção",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Serra tico-tico",
        "Serra elétrica para cortes",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Lixadeira",
        "Lixadeira elétrica",
        "un"
    ),

    (
        "Ferramentas elétricas",
        "Extensão elétrica",
        "Extensão elétrica para obra",
        "un"
    ),

    # CONCRETO

    (
        "Concreto",
        "Vibrador de concreto",
        "Equipamento para adensamento do concreto",
        "un"
    ),

    (
        "Concreto",
        "Betoneira",
        "Betoneira para mistura de concreto e argamassa",
        "un"
    ),

    (
        "Concreto",
        "Régua vibratória",
        "Régua para acabamento de concreto",
        "un"
    ),

    # ACESSO

    (
        "Acesso",
        "Escada de alumínio",
        "Escada para acesso em altura",
        "un"
    ),

    (
        "Acesso",
        "Escada extensível",
        "Escada extensível para serviços",
        "un"
    ),

    (
        "Acesso",
        "Andaime",
        "Estrutura modular para trabalho em altura",
        "un"
    ),

    # ACABAMENTO

    (
        "Acabamento",
        "Desempenadeira de aço",
        "Desempenadeira para acabamento",
        "un"
    ),

    (
        "Acabamento",
        "Desempenadeira de PVC",
        "Desempenadeira para acabamento",
        "un"
    ),

    (
        "Acabamento",
        "Rolo de pintura",
        "Rolo para pintura",
        "un"
    ),

    (
        "Acabamento",
        "Trincha",
        "Trincha para pintura",
        "un"
    ),

    (
        "Acabamento",
        "Espátula de aço",
        "Espátula para massa e acabamento",
        "un"
    ),

    (
        "Acabamento",
        "Raspador",
        "Raspador para preparação de superfície",
        "un"
    ),
]


def popular_ferramentas_iniciais():

    try:

        if Ferramenta.query.count() > 0:
            return

        for (
            categoria,
            nome,
            descricao,
            unidade
        ) in FERRAMENTAS_INICIAIS:

            db.session.add(
                Ferramenta(
                    categoria=categoria,
                    nome=nome,
                    descricao=descricao,
                    unidade=unidade,
                    estoque_minimo=0,
                    estoque_atual=0,
                    ativo=True,
                )
            )

        db.session.commit()

        logging.info(
            "Catálogo inicial de ferramentas criado."
        )

    except Exception:

        db.session.rollback()

        logging.exception(
            "Erro ao criar catálogo inicial de ferramentas."
        )


# ============================================================
# INICIALIZAÇÃO DO BANCO
# ============================================================

def inicializar_banco():

    """
    Inicializa e atualiza o banco sem apagar dados existentes.

    A função é chamada de forma controlada pelo primeiro request
    do Gunicorn/Render. Assim, uma falha de banco não derruba
    o processo do servidor durante o boot e não vira HTTP 502.
    """

    with app.app_context():

        try:

            logging.info(
                "Iniciando banco de dados..."
            )

            db.create_all()

            migrar_banco()

            popular_ferramentas_iniciais()

            if Empresa.query.count() == 0:

                empresa = Empresa(
                    razao_social="Empresa Demonstração",
                    nome_fantasia="Empresa Demonstração",
                    ativo=True,
                )

                db.session.add(
                    empresa
                )

                db.session.commit()

                logging.info(
                    "Empresa padrão criada."
                )

            admin_usuario = normalizar_usuario(
                os.getenv(
                    "ADMIN_USER",
                    "admin"
                )
            )

            admin_senha = os.getenv(
                "ADMIN_PASSWORD",
                "admin123"
            )

            admin = Usuario.query.filter_by(
                usuario=admin_usuario
            ).first()

            if not admin:

                admin = Usuario(
                    nome="Administrador Geral",
                    usuario=admin_usuario,
                    funcao="adm",
                    ativo=True,
                    empresa_id=None,
                )

                admin.definir_senha(
                    admin_senha
                )

                db.session.add(
                    admin
                )

                db.session.commit()

                logging.info(
                    "ADM geral criado."
                )

            elif admin.funcao != "adm":

                logging.warning(
                    "ADMIN_USER '%s' já existe, "
                    "mas não possui função ADM.",
                    admin_usuario
                )

            logging.info(
                "Banco de dados inicializado com sucesso."
            )

            return True

        except Exception:

            db.session.rollback()

            logging.exception(
                "Falha crítica ao inicializar/migrar "
                "o banco de dados."
            )

            return False


# ============================================================
# INICIALIZAÇÃO SOB DEMANDA
# ============================================================

_db_init_lock = threading.Lock()

_db_initialized = False


@app.before_request
def garantir_banco_inicializado():

    global _db_initialized

    if request.endpoint == "static":

        return None

    if _db_initialized:

        return None

    with _db_init_lock:

        if _db_initialized:

            return None

        sucesso = inicializar_banco()

        if not sucesso:

            return (
                render_template(
                    "error.html",
                    error_code=503,
                    error_title=(
                        "Banco de dados indisponível"
                    ),
                    error_message=(
                        "O sistema iniciou, mas não conseguiu "
                        "preparar o banco de dados. "
                        "Verifique a conexão DATABASE_URL "
                        "e os logs do Render."
                    ),
                ),
                503,
            )

        _db_initialized = True

    return None


# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def pagina_nao_encontrada(
    error
):

    return render_template(
        "error.html",
        error_code=404,
        error_title="Página não encontrada",
        error_message=(
            "A página que você tentou acessar "
            "não existe."
        )
    ), 404


@app.errorhandler(500)
def erro_interno(
    error
):

    try:

        db.session.rollback()

    except Exception:

        logging.exception(
            "Falha ao executar rollback "
            "no tratamento de erro."
        )

    logging.exception(
        "Erro interno da aplicação"
    )

    return render_template(
        "error.html",
        error_code=500,
        error_title="Erro interno",
        error_message=(
            "O sistema encontrou um erro interno. "
            "Tente novamente."
        )
    ), 500


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    inicializar_banco()

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
