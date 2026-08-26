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
    email = db.Column(db.String(120))   # para recuperación de contraseña
    rol = db.Column(db.String(20), default="operador")  # admin / operador / contador / lectura
    activo = db.Column(db.Boolean, default=True)
    # Obliga a cambiar la contraseña en el próximo ingreso (p.ej. admin inicial).
    must_change_password = db.Column(db.Boolean, default=False)
    # Segundo factor por email: si está activo, al ingresar pide un código de un
    # solo uso enviado al email del usuario (opt-in, recomendado para admins).
    dosfa_email = db.Column(db.Boolean, default=False, nullable=False,
                            server_default=db.text("false"))
    # Multiempresa: a qué inmobiliaria pertenece el usuario (None = superadmin de plataforma).
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def crear_admin_inicial():
        """Crea un usuario admin/admin123 si no existe ningún usuario.
        Queda obligado a cambiar la contraseña en el primer ingreso."""
        if Usuario.query.first() is None:
            admin = Usuario(username="admin", nombre="Administrador", rol="admin",
                            must_change_password=True)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

    def __repr__(self):
        return f"<Usuario {self.username}>"


# --------------------------------------------------------------------------- #
#  Inmobiliaria (tenant del SaaS multiempresa)
# --------------------------------------------------------------------------- #
class Inmobiliaria(db.Model):
    """Cada inmobiliaria es un 'tenant': ve y toca solo sus propios datos.

    Por ahora se usa el fundamento (toda entidad pertenece a una inmobiliaria y
    los datos actuales quedan asignados a la inmobiliaria #1). El filtrado de
    aislamiento entre inmobiliarias se activa en el paso siguiente."""
    __tablename__ = "inmobiliarias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False, default="Mi Inmobiliaria")
    slug = db.Column(db.String(60), unique=True)
    cuit = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    localidad = db.Column(db.String(120))
    telefono = db.Column(db.String(60))
    email = db.Column(db.String(120))
    logo_path = db.Column(db.String(300))
    plan = db.Column(db.String(20), default="inicial")
    activa = db.Column(db.Boolean, default=True)
    creada = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def principal():
        """La inmobiliaria por defecto (la primera). Durante la transición a
        multiempresa, todos los datos pertenecen a esta."""
        return Inmobiliaria.query.order_by(Inmobiliaria.id).first()

    @staticmethod
    def crear_inicial():
        """Crea la inmobiliaria #1 si no existe, tomando los datos de Ajustes."""
        if Inmobiliaria.query.first() is not None:
            return Inmobiliaria.query.order_by(Inmobiliaria.id).first()
        nombre = "Mi Inmobiliaria"
        cuit = direccion = localidad = telefono = None
        try:
            a = Ajustes.query.first()
            if a:
                nombre = a.nombre or nombre
                cuit, direccion = a.cuit, a.direccion
                localidad, telefono = a.localidad, a.telefono
        except Exception:
            pass
        inmo = Inmobiliaria(nombre=nombre, slug="principal", cuit=cuit,
                            direccion=direccion, localidad=localidad, telefono=telefono)
        db.session.add(inmo)
        db.session.commit()
        return inmo

    def __repr__(self):
        return f"<Inmobiliaria {self.nombre}>"


# --------------------------------------------------------------------------- #
#  Solicitudes de alta (auto-registro con aprobación del superadmin)
# --------------------------------------------------------------------------- #
class SolicitudAlta(db.Model):
    """Pedido de acceso de una inmobiliaria nueva. Queda pendiente hasta que el
    superadmin la aprueba (crea la inmobiliaria + su admin) o la rechaza."""
    __tablename__ = "solicitudes_alta"

    id = db.Column(db.Integer, primary_key=True)
    nombre_inmobiliaria = db.Column(db.String(160), nullable=False)
    nombre_contacto = db.Column(db.String(160))
    email = db.Column(db.String(120))
    telefono = db.Column(db.String(60))
    localidad = db.Column(db.String(120))
    username = db.Column(db.String(60), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    estado = db.Column(db.String(20), default="pendiente")   # pendiente/aprobada/rechazada
    creada = db.Column(db.DateTime, default=datetime.utcnow)
    procesada = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)


# --------------------------------------------------------------------------- #
#  Intentos de login (freno a la fuerza bruta)
# --------------------------------------------------------------------------- #
class IntentoLogin(db.Model):
    """Fallos de login recientes por IP + usuario.

    Viven en la base y no en memoria para que el límite valga para todos los
    workers del servidor y no se borre en cada reinicio o despliegue."""
    __tablename__ = "intentos_login"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(160), unique=True, nullable=False, index=True)
    fallos = db.Column(db.Integer, nullable=False, default=0)
    ultimo = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# --------------------------------------------------------------------------- #
#  Auditoría (quién hizo qué y cuándo)
# --------------------------------------------------------------------------- #
class RegistroAuditoria(db.Model):
    """Bitácora de altas, cambios y eliminaciones. Se llena automáticamente."""
    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario_id = db.Column(db.Integer)
    usuario_nombre = db.Column(db.String(120))
    accion = db.Column(db.String(20))     # crear / editar / eliminar
    entidad = db.Column(db.String(40))    # Contrato / Pago / Persona / ...
    entidad_id = db.Column(db.String(20))
    descripcion = db.Column(db.String(300))
    ip = db.Column(db.String(50))

    def __repr__(self):
        return f"<Auditoria {self.accion} {self.entidad} {self.entidad_id}>"


# --------------------------------------------------------------------------- #
#  Personas (propietarios e inquilinos)
# --------------------------------------------------------------------------- #
class Persona(db.Model):
    __tablename__ = "personas"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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
    cuenta_gas = db.Column(db.String(30))                 # N° de cliente en Litoral Gas (ej. 962500/01)
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
# Tablas puente para sumar MÁS personas de cada lado del contrato (además del
# inquilino y el propietario "titulares", que se siguen usando para cobros,
# recibos y liquidaciones). Estas solo agregan co-firmantes al documento.
contrato_colocatarios = db.Table(
    "contrato_colocatarios",
    db.Column("contrato_id", db.Integer, db.ForeignKey("contratos.id"), primary_key=True),
    db.Column("persona_id", db.Integer, db.ForeignKey("personas.id"), primary_key=True),
)
contrato_colocadores = db.Table(
    "contrato_colocadores",
    db.Column("contrato_id", db.Integer, db.ForeignKey("contratos.id"), primary_key=True),
    db.Column("persona_id", db.Integer, db.ForeignKey("personas.id"), primary_key=True),
)


class Contrato(db.Model):
    __tablename__ = "contratos"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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
    # Fecha desde la que se cuenta el próximo aumento (ej: cuando el precio actual
    # empezó a regir). Útil para datos importados sin historial de aumentos: sin
    # esto, el próximo aumento se contaría desde el inicio del contrato.
    aumento_base = db.Column(db.Date)

    estado = db.Column(db.String(20), default="Vigente")  # Vigente/Finalizado/Rescindido
    aumento_pospuesto = db.Column(db.Date)                 # no recordar el aumento hasta esta fecha
    origen = db.Column(db.String(20), default="manual")   # manual / generador
    documento_html = db.Column(db.Text)                   # contrato generado (para reimprimir)
    observaciones = db.Column(db.Text)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    inmueble = db.relationship("Inmueble", back_populates="contratos")
    inquilino = db.relationship("Persona", foreign_keys=[inquilino_id])
    propietario = db.relationship("Persona", foreign_keys=[propietario_id])
    # Co-firmantes adicionales (opcionales) de cada lado.
    colocatarios = db.relationship("Persona", secondary=contrato_colocatarios)
    colocadores = db.relationship("Persona", secondary=contrato_colocadores)
    fiadores = db.relationship("Fiador", back_populates="contrato",
                               cascade="all, delete-orphan")
    aumentos = db.relationship("Aumento", back_populates="contrato",
                               cascade="all, delete-orphan")
    pagos = db.relationship("Pago", back_populates="contrato",
                            cascade="all, delete-orphan")

    # --- Partes completas de cada lado (titular + co-firmantes, sin repetir) ---
    @property
    def locatarios(self):
        out = []
        if self.inquilino:
            out.append(self.inquilino)
        for p in self.colocatarios:
            if p and p.id != self.inquilino_id:
                out.append(p)
        return out

    @property
    def locadores(self):
        out = []
        prin = self.propietario or (self.inmueble.propietario if self.inmueble else None)
        if prin:
            out.append(prin)
        prin_id = prin.id if prin else None
        for p in self.colocadores:
            if p and p.id != prin_id:
                out.append(p)
        return out

    @property
    def locatarios_texto(self):
        nombres = [p.nombre for p in self.locatarios if p and p.nombre]
        return " y ".join(nombres) if nombres else "—"

    @property
    def locadores_texto(self):
        nombres = [p.nombre for p in self.locadores if p and p.nombre]
        return " y ".join(nombres) if nombres else "—"

    def __repr__(self):
        return f"<Contrato {self.numero or self.id}>"


class DocumentoContrato(db.Model):
    """Documentación adjunta a un contrato (DNI, recibos de sueldo, etc.).
    El archivo se guarda dentro de la base para que no se pierda en la nube."""
    __tablename__ = "documentos_contrato"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"),
                            nullable=False, index=True)
    categoria = db.Column(db.String(40))        # DNI / Recibo de sueldo / Garantía / Otro
    persona = db.Column(db.String(160))          # a quién pertenece (texto libre)
    nombre_archivo = db.Column(db.String(255))
    tipo_mime = db.Column(db.String(100))
    tamano = db.Column(db.Integer)
    datos = db.Column(db.LargeBinary)
    subido_por = db.Column(db.String(120))
    subido = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship("Contrato", backref=db.backref(
        "documentos", cascade="all, delete-orphan",
        order_by="DocumentoContrato.subido"))

    @property
    def es_imagen(self):
        return (self.tipo_mime or "").startswith("image/")

    @property
    def tamano_texto(self):
        kb = (self.tamano or 0) / 1024
        return f"{kb/1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


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
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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

    # Un solo pago por contrato y período: evita duplicar un cobro (doble clic /
    # dos operaciones simultáneas). Los saldos se completan con "abonar", no con
    # un pago nuevo del mismo período.
    # Y un número de recibo irrepetible dentro de la inmobiliaria: si dos cobros
    # simultáneos alcanzan a tomar el mismo número, el segundo commit falla y se
    # reintenta, en vez de emitir dos recibos con la misma numeración.
    # Un solo pago ACTIVO por contrato y período: un pago anulado deja libre el
    # período para volver a cobrarlo, pero se conserva como rastro (índice parcial).
    __table_args__ = (
        db.Index("uq_pago_contrato_periodo",
                 "contrato_id", "periodo_mes", "periodo_anio", unique=True,
                 sqlite_where=db.text("estado <> 'Anulado'"),
                 postgresql_where=db.text("estado <> 'Anulado'")),
        db.UniqueConstraint("inmobiliaria_id", "recibo_numero",
                            name="uq_pago_recibo_numero"),
    )

    @property
    def anulado(self):
        return self.estado == "Anulado"


class GastoExtra(db.Model):
    __tablename__ = "gastos_extra"

    id = db.Column(db.Integer, primary_key=True)
    pago_id = db.Column(db.Integer, db.ForeignKey("pagos.id"), nullable=False)
    descripcion = db.Column(db.String(120))               # Agua, Expensas, Descuento...
    monto = db.Column(db.Numeric(14, 2))                  # negativo = descuento
    # Si es True, el importe se traslada al propietario en la liquidación (además
    # del alquiler, sin comisión). Si es False, queda afuera: lo cobramos junto con
    # el alquiler pero es plata nuestra (ej.: un seguro que pagamos nosotros), no
    # del propietario. Default True: mantiene el criterio de "esto es del
    # propietario salvo que se diga lo contrario" para cosas como agua o expensas.
    trasladar_liquidacion = db.Column(db.Boolean, default=True, nullable=False,
                                      server_default=db.text("true"))

    pago = db.relationship("Pago", back_populates="gastos")


class SeguimientoNota(db.Model):
    """Nota de seguimiento de un contrato: gestiones, llamados, reclamos, acuerdos
    o cualquier cuestión relativa al caso. Queda con autor y fecha."""
    __tablename__ = "seguimiento_notas"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"),
                                index=True, nullable=False)
    contrato_id = db.Column(db.Integer, db.ForeignKey("contratos.id"),
                            nullable=False, index=True)
    texto = db.Column(db.Text, nullable=False)
    autor = db.Column(db.String(80))
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    contrato = db.relationship("Contrato", backref=db.backref(
        "seguimiento_notas", cascade="all, delete-orphan",
        order_by="SeguimientoNota.creado.desc()"))


class TareaPendiente(db.Model):
    """Recordatorio de una acción pendiente de la inmobiliaria (llamar a alguien,
    ir al banco, mandar un contrato...). Se tilda al completarla y deja de figurar."""
    __tablename__ = "tareas_pendientes"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"),
                                index=True, nullable=False)
    texto = db.Column(db.String(300), nullable=False)
    autor = db.Column(db.String(80))
    creado = db.Column(db.DateTime, default=datetime.utcnow)
    completada = db.Column(db.Boolean, default=False, nullable=False,
                           server_default=db.text("false"))
    completada_en = db.Column(db.DateTime)
    completada_por = db.Column(db.String(80))


# --------------------------------------------------------------------------- #
#  Ajustes de la inmobiliaria (fila única)
# --------------------------------------------------------------------------- #
class Ajustes(db.Model):
    __tablename__ = "ajustes"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, index=True)   # cada inmobiliaria tiene sus ajustes
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
    # Credenciales de Litoral Gas (por inmobiliaria). La clave se guarda cifrada.
    gas_usuario = db.Column(db.String(160))
    gas_clave_enc = db.Column(db.Text)
    # Facturación electrónica ARCA (multiempresa): token del emisor (cifrado) + datos de referencia.
    facturador_token_enc = db.Column(db.Text)
    facturador_modo = db.Column(db.String(16))
    facturador_pv = db.Column(db.Integer)

    @staticmethod
    def get():
        # Con el filtro multiempresa activo, .first() ya devuelve los ajustes de
        # la inmobiliaria del usuario logueado. Si no existen todavía, se crean
        # (el before_flush les asigna la inmobiliaria correcta).
        a = Ajustes.query.first()
        if a is None:
            a = Ajustes()
            db.session.add(a)
            db.session.commit()
        return a

    def set_gas_clave(self, clave):
        from .cripto import cifrar
        self.gas_clave_enc = cifrar(clave)

    def get_gas_clave(self):
        from .cripto import descifrar
        return descifrar(self.gas_clave_enc)

    @property
    def gas_configurado(self):
        return bool(self.gas_usuario and self.gas_clave_enc)

    def set_facturador_token(self, token):
        from .cripto import cifrar
        self.facturador_token_enc = cifrar(token)

    def get_facturador_token(self):
        from .cripto import descifrar
        return descifrar(self.facturador_token_enc)

    @property
    def facturador_configurado(self):
        return bool(self.facturador_token_enc)

    def _bloquear(self):
        """Devuelve esta fila de Ajustes con bloqueo de escritura, para que dos
        cobros/liquidaciones simultáneos no tomen el mismo número. En PostgreSQL
        usa SELECT ... FOR UPDATE; en SQLite es inocuo."""
        try:
            obj = (Ajustes.query.filter_by(id=self.id)
                   .with_for_update().first())
            return obj or self
        except Exception:
            return self

    def siguiente_recibo(self):
        obj = self._bloquear()
        num = obj.recibo_proximo or 1
        obj.recibo_proximo = num + 1
        self.recibo_proximo = obj.recibo_proximo
        return f"{obj.recibo_prefijo or '0001'}-{num:08d}"

    def siguiente_liquidacion(self):
        obj = self._bloquear()
        num = obj.liquidacion_proximo or 1
        obj.liquidacion_proximo = num + 1
        self.liquidacion_proximo = obj.liquidacion_proximo
        return f"{obj.liquidacion_prefijo or '0001'}-{num:08d}"


class GasEstado(db.Model):
    """Estado de deuda de gas por cuenta de Litoral Gas (lo llena el robot)."""
    __tablename__ = "gas_estado"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
    cuenta = db.Column(db.String(30), unique=True, nullable=False)  # N° de cliente (962500/01)
    titular = db.Column(db.String(160))
    direccion = db.Column(db.String(200))
    contrato_vigente = db.Column(db.Boolean, default=True)   # "Contrato vigente" en Litoral Gas
    tiene_deuda = db.Column(db.Boolean, default=False)
    deuda_total = db.Column(db.Numeric(14, 2), default=0)
    ultimo_vencimiento = db.Column(db.Date)
    detalle = db.Column(db.Text)               # JSON o texto con las facturas pendientes
    actualizado = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def upsert(cuenta, **datos):
        g = GasEstado.query.filter_by(cuenta=cuenta).first()
        if not g:
            g = GasEstado(cuenta=cuenta)
            db.session.add(g)
        for k, v in datos.items():
            setattr(g, k, v)
        g.actualizado = datetime.utcnow()
        return g


class GasCredencial(db.Model):
    """Una cuenta de Litoral Gas por inmobiliaria (soporta varias). La clave se
    guarda cifrada; se usa para consultar la deuda desde el servidor."""
    __tablename__ = "gas_credenciales"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"),
                                index=True, nullable=False)
    alias = db.Column(db.String(80))
    usuario = db.Column(db.String(160), nullable=False)
    clave_enc = db.Column(db.Text, nullable=False)
    creada = db.Column(db.DateTime, default=datetime.utcnow)

    def set_clave(self, clave):
        from .cripto import cifrar
        self.clave_enc = cifrar(clave)

    def get_clave(self):
        from .cripto import descifrar
        return descifrar(self.clave_enc)


class ReciboManual(db.Model):
    __tablename__ = "recibos_manuales"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"), index=True, nullable=False)
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

    # Comprobante de honorarios emitido por el facturador (se guarda para poder
    # verlo después sin salir del gestor y para la bandeja de "sin facturar").
    factura_estado = db.Column(db.String(24))   # emitida/error/sin_cuit/requiere_confirmacion/...
    factura_id = db.Column(db.Integer)          # id en el facturador (para el PDF)
    factura_numero = db.Column(db.String(30))
    factura_tipo = db.Column(db.String(10))     # C / A / B / 11...
    factura_cae = db.Column(db.String(20))
    factura_cae_vto = db.Column(db.Date)
    factura_fecha = db.Column(db.Date)
    factura_detalle = db.Column(db.Text)        # mensaje de error si no se pudo emitir

    propietario = db.relationship("Persona")
    conceptos = db.relationship("ConceptoLiquidacion", back_populates="liquidacion",
                                cascade="all, delete-orphan", order_by="ConceptoLiquidacion.id")

    @property
    def facturada(self):
        return self.factura_estado == "emitida"

    @property
    def conceptos_total(self):
        """Suma de los conceptos extra (+ suma / − resta al neto del propietario)."""
        return float(sum(float(c.monto or 0) for c in self.conceptos))


class ConceptoLiquidacion(db.Model):
    """Línea extra en una liquidación: un concepto libre con importe (+ suma / − resta
    al neto que se le paga al propietario). Ej.: reparación, expensas, reintegro."""
    __tablename__ = "conceptos_liquidacion"

    id = db.Column(db.Integer, primary_key=True)
    inmobiliaria_id = db.Column(db.Integer, db.ForeignKey("inmobiliarias.id"),
                                index=True, nullable=False)
    liquidacion_id = db.Column(db.Integer,
                               db.ForeignKey("liquidaciones.id", ondelete="CASCADE"),
                               index=True, nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    liquidacion = db.relationship("Liquidacion", back_populates="conceptos")


class OperacionIdem(db.Model):
    """Huella de operaciones de plata ya ejecutadas (clave de idempotencia).

    El único por período frena el pago duplicado, pero no el pago *a cuenta*, que
    suma plata sobre un pago que ya existe: ahí un doble clic cobra dos veces. Los
    formularios de plata llevan una clave que se reserva en la misma transacción
    que la operación; si el pedido llega repetido, la clave ya está tomada y no se
    vuelve a cobrar.
    """
    __tablename__ = "operaciones_idem"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(120), unique=True, nullable=False, index=True)
    creado = db.Column(db.DateTime, default=datetime.utcnow)
