"""Modelo de datos completo del sistema de gestión de alquileres.

Aunque el Sprint 1 solo usa Usuario, Persona e Inmueble, se define todo el
esquema desde el inicio para que la base sea coherente y los próximos sprints
(contratos, cobros, aumentos, recibos) se apoyen sobre estas tablas.
"""
from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db


# --------------------------------------------------------------------------- #
#  Usuarios / autenticación
# --------------------------------------------------------------------------- #
class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(120))
    rol = db.Column(db.String(20), default="operador")  # admin / operador
    activo = db.Column(db.Boolean, default=True)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def crear_admin_inicial():
        """Crea un usuario admin/admin123 si no existe ningún usuario."""
        if Usuario.query.first() is None:
            admin = Usuario(username="admin", nombre="Administrador", rol="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

    def __repr__(self):
        return f"<Usuario {self.username}>"


# --------------------------------------------------------------------------- #
#  Personas (propietarios e inquilinos)
# --------------------------------------------------------------------------- #
class Persona(db.Model):
    __tablename__ = "personas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False)
    dni = db.Column(db.String(20))
    cuit = db.Column(db.String(20))
    domicilio = db.Column(db.String(200))
    localidad = db.Column(db.String(120))
    telefono = db.Column(db.String(60))
    email = db.Column(db.String(120))
    cond_iva = db.Column(db.String(40), default="Consumidor Final")
    es_propietario = db.Column(db.Boolean, default=False)
    es_inquilino = db.Column(db.Boolean, default=False)
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    inmuebles = db.relationship("Inmueble", back_populates="propietario",
                                foreign_keys="Inmueble.propietario_id")

    @property
    def roles_texto(self):
        roles = []
        if self.es_propietario:
            roles.append("Propietario")
        if self.es_inquilino:
            roles.append("Inquilino")
        return " / ".join(roles) if roles else "—"

    def __repr__(self):
        return f"<Persona {self.nombre}>"


# --------------------------------------------------------------------------- #
#  Inmuebles
# --------------------------------------------------------------------------- #
class Inmueble(db.Model):
    __tablename__ = "inmuebles"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True)         # ej. DE17, CA3
    tipo = db.Column(db.String(40))                        # Casa, Departamento, Local...
    direccion = db.Column(db.String(200), nullable=False)
    localidad = db.Column(db.String(120))
    provincia = db.Column(db.String(120))
    barrio = db.Column(db.String(120))
    dormitorios = db.Column(db.Integer)
    banos = db.Column(db.Integer)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(20), default="Disponible")  # Disponible/Alquilado/Reservado
    moneda = db.Column(db.String(10), default="Pesos")
    precio_referencia = db.Column(db.Numeric(14, 2))
    comision_pct = db.Column(db.Numeric(12, 2))            # % que se cobra al propietario
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    propietario_id = db.Column(db.Integer, db.ForeignKey("personas.id"))
    propietario = db.relationship("Persona", back_populates="inmuebles",
                                  foreign_keys=[propietario_id])

    contratos = db.relationship("Contrato", back_populates="inmueble")

    def __repr__(self):
        return f"<Inmueble {self.codigo} {self.direccion}>"


# --------------------------------------------------------------------------- #
#  Contratos de alquiler
# --------------------------------------------------------------------------- #
class Contrato(db.Model):
    __tablename__ = "contratos"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30))                     # numeración interna
    inmueble_id = db.Column(db.Integer, db.ForeignKey("inmuebles.id"), nullable=False)
    inquilino_id = db.Column(db.Integer, db.ForeignKey("personas.id"), nullable=False)
    propietario_id = db.Column(db.Integer, db.ForeignKey("personas.id"))

    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date)
    duracion_meses = db.Column(db.Integer)
    precio_inicial = db.Column(db.Numeric(14, 2), nullable=False)
    precio_actual = db.Column(db.Numeric(14, 2))          # se actualiza con los aumentos
    moneda = db.Column(db.String(10), default="Pesos")

    dia_vencimiento = db.Column(db.Integer, default=10)
    mora_diaria_pct = db.Column(db.Numeric(8, 3), default=0)
    comision_pct = db.Column(db.Numeric(12, 2))           # % comisión de este contrato
                                                          # (si es None, usa la del inmueble)

    # Ajustes / aumentos
    metodo_ajuste = db.Column(db.String(20), default="porcentaje")  # indice/porcentaje/sin_ajuste
    indice_tipo = db.Column(db.String(20))                # ICL / IPC / CasaPropia
    ajuste_cada_meses = db.Column(db.Integer, default=6)
    porcentaje_ajuste = db.Column(db.Numeric(8, 2))       # % por período (método porcentaje)

    estado = db.Column(db.String(20), default="Vigente")  # Vigente/Finalizado/Rescindido
    origen = db.Column(db.String(20), default="manual")   # manual / generador
    documento_html = db.Column(db.Text)                   # contrato generado (para reimprimir)
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    inmueble = db.relationship("Inmueble", back_populates="contratos")
    inquilino = db.relationship("Persona", foreign_keys=[inquilino_id])
    propietario = db.relationship("Persona", foreign_keys=[propietario_id])
    fiadores = db.relationship("Fiador", back_populates="contrato",
                               cascade="all, delete-orphan")
    aumentos = db.relationship("Aumento", back_populates="contrato",
                               cascade="all, delete-orphan")
    pagos = db.relationship("Pago", back_populates="contrato",
                            cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Contrato {self.numero or self.id}>"


class Fiador(db.Model):
    __tablename__ = "fiadores"

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    nombre = db.Column(db.String(160), nullable=False)
    dni = db.Column(db.String(20))
    domicilio = db.Column(db.String(200))
    telefono = db.Column(db.String(60))
    email = db.Column(db.String(120))
    solvencia = db.Column(db.String(250))   # "Acredita solvencia con..." (trabajo, inmueble, etc.)

    contrato = db.relationship("Contrato", back_populates="fiadores")


# --------------------------------------------------------------------------- #
#  Aumentos aplicados
# --------------------------------------------------------------------------- #
class Aumento(db.Model):
    __tablename__ = "aumentos"

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    fecha_vigencia = db.Column(db.Date, nullable=False)
    precio_anterior = db.Column(db.Numeric(14, 2))
    precio_nuevo = db.Column(db.Numeric(14, 2))
    metodo = db.Column(db.String(20))                     # indice / porcentaje
    indice_tipo = db.Column(db.String(20))
    indice_inicio = db.Column(db.Numeric(16, 6))
    indice_fin = db.Column(db.Numeric(16, 6))
    porcentaje = db.Column(db.Numeric(8, 2))
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship("Contrato", back_populates="aumentos")


# --------------------------------------------------------------------------- #
#  Valores de índices oficiales (ICL / IPC / Casa Propia)
# --------------------------------------------------------------------------- #
class IndiceValor(db.Model):
    __tablename__ = "indices_valores"
    __table_args__ = (db.UniqueConstraint("tipo", "periodo", name="uq_indice_periodo"),)

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)       # ICL / IPC / CasaPropia
    periodo = db.Column(db.Date, nullable=False)          # primer día del mes
    valor = db.Column(db.Numeric(16, 6), nullable=False)
    fuente = db.Column(db.String(40))                     # BCRA / INDEC / manual
    creado = db.Column(db.DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------- #
#  Pagos / cobros
# --------------------------------------------------------------------------- #
class Pago(db.Model):
    __tablename__ = "pagos"

    id = db.Column(db.Integer, primary_key=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"), nullable=False)
    numero = db.Column(db.Integer)                        # nro de pago dentro del contrato
    periodo_mes = db.Column(db.Integer)                   # 1-12
    periodo_anio = db.Column(db.Integer)
    fecha_pago = db.Column(db.Date)
    precio_alquiler = db.Column(db.Numeric(14, 2))
    mora = db.Column(db.Numeric(14, 2), default=0)
    total = db.Column(db.Numeric(14, 2))
    pagado = db.Column(db.Numeric(14, 2), default=0)
    saldo = db.Column(db.Numeric(14, 2), default=0)
    moneda = db.Column(db.String(10), default="Pesos")
    forma_pago = db.Column(db.String(60))
    pagado_al_propietario = db.Column(db.Date)
    recibo_numero = db.Column(db.String(30))
    estado = db.Column(db.String(20), default="Pendiente")  # Pagado/Pendiente/Parcial
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship("Contrato", back_populates="pagos")
    gastos = db.relationship("GastoExtra", back_populates="pago",
                             cascade="all, delete-orphan")


class GastoExtra(db.Model):
    __tablename__ = "gastos_extra"

    id = db.Column(db.Integer, primary_key=True)
    pago_id = db.Column(db.Integer, db.ForeignKey("pagos.id"), nullable=False)
    descripcion = db.Column(db.String(120))               # Agua, Expensas, Descuento...
    monto = db.Column(db.Numeric(14, 2))                  # negativo = descuento

    pago = db.relationship("Pago", back_populates="gastos")


# --------------------------------------------------------------------------- #
#  Ajustes de la inmobiliaria (fila única)
# --------------------------------------------------------------------------- #
class Ajustes(db.Model):
    __tablename__ = "ajustes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), default="Mi Inmobiliaria")
    cuit = db.Column(db.String(20))
    ing_brutos = db.Column(db.String(30))
    inicio_actividades = db.Column(db.String(30))
    cond_iva = db.Column(db.String(40), default="Responsable Monotributo")
    direccion = db.Column(db.String(200))
    localidad = db.Column(db.String(120))
    telefono = db.Column(db.String(60))
    horario = db.Column(db.String(120))
    logo_url = db.Column(db.String(300))
    recibo_prefijo = db.Column(db.String(8), default="0001")
    recibo_proximo = db.Column(db.Integer, default=1)
    liquidacion_prefijo = db.Column(db.String(8), default="0001")
    liquidacion_proximo = db.Column(db.Integer, default=1)
    pagare_meses = db.Column(db.Integer, default=10)
    pagare_lugar = db.Column(db.String(120))

    @staticmethod
    def get():
        a = Ajustes.query.first()
        if a is None:
            a = Ajustes()
            db.session.add(a)
            db.session.commit()
        return a

    def siguiente_recibo(self):
        num = self.recibo_proximo or 1
        self.recibo_proximo = num + 1
        return f"{self.recibo_prefijo or '0001'}-{num:08d}"

    def siguiente_liquidacion(self):
        num = self.liquidacion_proximo or 1
        self.liquidacion_proximo = num + 1
        return f"{self.liquidacion_prefijo or '0001'}-{num:08d}"


class ReciboManual(db.Model):
    __tablename__ = "recibos_manuales"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30))
    fecha = db.Column(db.Date)
    cliente = db.Column(db.String(160), nullable=False)
    cliente_dni = db.Column(db.String(20))
    cliente_domicilio = db.Column(db.String(200))
    concepto_general = db.Column(db.String(200))          # "En concepto de..."
    detalle = db.Column(db.Text)                          # conceptos, uno por línea "desc | monto"
    total = db.Column(db.Numeric(14, 2))
    moneda = db.Column(db.String(10), default="Pesos")
    forma_pago = db.Column(db.String(60))
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)


class PagareManual(db.Model):
    __tablename__ = "pagares_manuales"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date)
    lugar = db.Column(db.String(120))
    beneficiario = db.Column(db.String(160))              # a la orden de...
    deudor = db.Column(db.String(160), nullable=False)    # quien firma / paga
    deudor_dni = db.Column(db.String(20))
    deudor_domicilio = db.Column(db.String(200))
    monto = db.Column(db.Numeric(14, 2))                  # monto de cada pagaré
    moneda = db.Column(db.String(10), default="Pesos")
    cantidad = db.Column(db.Integer, default=1)
    primer_venc = db.Column(db.Date)                      # vencimiento del 1º (o None = a la vista)
    cada_dias = db.Column(db.Integer, default=30)         # separación entre vencimientos
    concepto = db.Column(db.String(200))
    creado = db.Column(db.DateTime, default=datetime.utcnow)


class Liquidacion(db.Model):
    __tablename__ = "liquidaciones"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30))
    fecha = db.Column(db.Date)
    periodo_mes = db.Column(db.Integer)
    periodo_anio = db.Column(db.Integer)
    propietario_id = db.Column(db.Integer, db.ForeignKey("personas.id"))
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"))  # None = todas juntas
    moneda = db.Column(db.String(10), default="Pesos")
    total_ingresos = db.Column(db.Numeric(14, 2))
    total_comision = db.Column(db.Numeric(14, 2))
    total_neto = db.Column(db.Numeric(14, 2))
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    propietario = db.relationship("Persona")
