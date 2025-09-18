from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuración de base de datos
if os.environ.get('DATABASE_URL'):
    # Para producción (Render)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
else:
    # Para desarrollo local
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:password@localhost:5432/gym_tracker'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelos de base de datos
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    registros = db.relationship('RegistroEjercicio', backref='usuario', lazy=True)
    registros_peso = db.relationship('RegistroPeso', backref='usuario', lazy=True)
    ejercicios_personalizados = db.relationship('Ejercicio', backref='creador', lazy=True)

class Ejercicio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    grupo_muscular = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)  # Null = ejercicio del sistema
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)  # Para poder "eliminar" sin borrar registros
    
    # Relaciones
    registros = db.relationship('RegistroEjercicio', backref='ejercicio', lazy=True)

class RegistroEjercicio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    ejercicio_id = db.Column(db.Integer, db.ForeignKey('ejercicio.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)  # Fecha del ejercicio
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)  # Cuándo se registró
    notas = db.Column(db.Text)
    
    # Relación con las series individuales
    series = db.relationship('SerieEjercicio', backref='registro', lazy=True, cascade='all, delete-orphan')

class SerieEjercicio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey('registro_ejercicio.id'), nullable=False)
    numero_serie = db.Column(db.Integer, nullable=False)  # 1, 2, 3, etc.
    peso = db.Column(db.Float, nullable=False)
    repeticiones = db.Column(db.Integer, nullable=False)
    completada = db.Column(db.Boolean, default=True)  # Si la serie se completó

class RegistroPeso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    peso = db.Column(db.Float, nullable=False)  # Peso en kg
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    notas = db.Column(db.Text)  # Observaciones opcionales

# Rutas
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and check_password_hash(usuario.password_hash, password):
            session['user_id'] = usuario.id
            session['username'] = usuario.username
            flash('Bienvenido!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Verificar si el usuario ya existe
        if Usuario.query.filter_by(username=username).first():
            flash('El usuario ya existe', 'error')
            return render_template('register.html')
        
        if Usuario.query.filter_by(email=email).first():
            flash('El email ya está registrado', 'error')
            return render_template('register.html')
        
        # Crear nuevo usuario
        nuevo_usuario = Usuario(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        flash('Registro exitoso! Ahora puedes iniciar sesión', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Obtener ejercicios del sistema (usuario_id es NULL) + ejercicios personalizados del usuario
    ejercicios_sistema = Ejercicio.query.filter_by(usuario_id=None, activo=True).all()
    ejercicios_personalizados = Ejercicio.query.filter_by(usuario_id=session['user_id'], activo=True).all()
    
    # Combinar ambos tipos de ejercicios
    todos_ejercicios = ejercicios_sistema + ejercicios_personalizados
    
    # Agrupar ejercicios por grupo muscular
    ejercicios_agrupados = {}
    for ejercicio in todos_ejercicios:
        grupo = ejercicio.grupo_muscular
        if grupo not in ejercicios_agrupados:
            ejercicios_agrupados[grupo] = []
        ejercicios_agrupados[grupo].append(ejercicio)
    
    # Ordenar los grupos musculares
    grupos_ordenados = sorted(ejercicios_agrupados.keys())
    
    # Obtener últimos registros del usuario
    ultimos_registros = RegistroEjercicio.query.filter_by(
        usuario_id=session['user_id']
    ).order_by(RegistroEjercicio.fecha_registro.desc()).limit(10).all()
    
    # Fecha de hoy para el formulario
    today = date.today().strftime('%Y-%m-%d')
    
    # Obtener solo ejercicios personalizados para la gestión
    ejercicios_personalizados_activos = ejercicios_personalizados
    
    return render_template('dashboard.html', 
                         ejercicios=todos_ejercicios,
                         ejercicios_agrupados=ejercicios_agrupados,
                         grupos_ordenados=grupos_ordenados,
                         ultimos_registros=ultimos_registros,
                         ejercicios_personalizados=ejercicios_personalizados_activos,
                         today=today)

@app.route('/registrar_ejercicio', methods=['POST'])
def registrar_ejercicio():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    ejercicio_id = request.form['ejercicio_id']
    notas = request.form.get('notas', '')
    
    # Obtener la fecha del ejercicio
    fecha_ejercicio = request.form.get('fecha')
    if fecha_ejercicio:
        fecha_ejercicio = datetime.strptime(fecha_ejercicio, '%Y-%m-%d').date()
    else:
        fecha_ejercicio = date.today()
    
    # Crear el registro principal del ejercicio
    nuevo_registro = RegistroEjercicio(
        usuario_id=session['user_id'],
        ejercicio_id=ejercicio_id,
        fecha=fecha_ejercicio,
        notas=notas
    )
    
    db.session.add(nuevo_registro)
    db.session.flush()  # Para obtener el ID sin hacer commit
    
    # Procesar las series individuales
    series_data = request.form.getlist('series_data')
    for i, serie_json in enumerate(series_data):
        if serie_json:  # Si hay datos para esta serie
            import json
            try:
                serie_data = json.loads(serie_json)
                nueva_serie = SerieEjercicio(
                    registro_id=nuevo_registro.id,
                    numero_serie=i + 1,
                    peso=float(serie_data['peso']),
                    repeticiones=int(serie_data['repeticiones']),
                    completada=serie_data.get('completada', True)
                )
                db.session.add(nueva_serie)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
    
    db.session.commit()
    
    flash('Ejercicio registrado exitosamente!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/registrar_peso', methods=['POST'])
def registrar_peso():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    peso = float(request.form['peso'])
    notas = request.form.get('notas_peso', '')
    
    # Obtener la fecha
    fecha_peso = request.form.get('fecha_peso')
    if fecha_peso:
        fecha_peso = datetime.strptime(fecha_peso, '%Y-%m-%d').date()
    else:
        fecha_peso = date.today()
    
    # Verificar si ya existe un registro para esta fecha
    registro_existente = RegistroPeso.query.filter_by(
        usuario_id=session['user_id'],
        fecha=fecha_peso
    ).first()
    
    if registro_existente:
        # Actualizar el registro existente
        registro_existente.peso = peso
        registro_existente.notas = notas
        registro_existente.fecha_registro = datetime.utcnow()
        flash('Peso actualizado correctamente!', 'success')
    else:
        # Crear nuevo registro
        nuevo_registro = RegistroPeso(
            usuario_id=session['user_id'],
            peso=peso,
            fecha=fecha_peso,
            notas=notas
        )
        db.session.add(nuevo_registro)
        flash('Peso registrado exitosamente!', 'success')
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/peso_data')
def peso_data():
    if 'user_id' not in session:
        return {'error': 'No autenticado'}, 401
    
    # Obtener parámetros de filtro
    dias = request.args.get('dias', 30, type=int)
    fecha_limite = date.today() - timedelta(days=dias)
    
    # Obtener registros de peso
    registros = RegistroPeso.query.filter_by(
        usuario_id=session['user_id']
    ).filter(
        RegistroPeso.fecha >= fecha_limite
    ).order_by(RegistroPeso.fecha.asc()).all()
    
    # Preparar datos para la gráfica
    datos = []
    for registro in registros:
        datos.append({
            'fecha': registro.fecha.strftime('%Y-%m-%d'),
            'peso': float(registro.peso),
            'notas': registro.notas or ''
        })
    
    return {
        'datos': datos,
        'periodo': f'Últimos {dias} días',
        'peso_actual': datos[-1]['peso'] if datos else None,
        'peso_inicial': datos[0]['peso'] if datos else None,
        'diferencia': (datos[-1]['peso'] - datos[0]['peso']) if len(datos) > 1 else 0
    }

@app.route('/progreso_ejercicio/<int:ejercicio_id>')
def progreso_ejercicio(ejercicio_id):
    """Obtener datos de progreso para un ejercicio específico (para gráficas)"""
    if 'user_id' not in session:
        return {'error': 'No autenticado'}, 401
    
    # Obtener parámetros de filtro
    dias = request.args.get('dias', 90, type=int)  # Por defecto 3 meses para ejercicios
    fecha_limite = date.today() - timedelta(days=dias)
    
    # Obtener registros del ejercicio ordenados por fecha
    registros = RegistroEjercicio.query.filter_by(
        usuario_id=session['user_id'],
        ejercicio_id=ejercicio_id
    ).filter(
        RegistroEjercicio.fecha >= fecha_limite
    ).order_by(RegistroEjercicio.fecha.asc()).all()
    
    # Preparar datos para gráficas
    datos = []
    for registro in registros:
        if registro.series:  # Si tiene series registradas
            # Ordenar series por número
            series_ordenadas = sorted(registro.series, key=lambda x: x.numero_serie)
            
            # Obtener peso de la primera serie (indicador principal)
            primera_serie = series_ordenadas[0] if series_ordenadas else None
            
            if primera_serie:
                # Calcular métricas del registro completo
                peso_max = max(serie.peso for serie in registro.series)
                peso_promedio = sum(serie.peso for serie in registro.series) / len(registro.series)
                repeticiones_total = sum(serie.repeticiones for serie in registro.series)
                volumen_total = sum(serie.peso * serie.repeticiones for serie in registro.series)
                
                datos.append({
                    'fecha': registro.fecha.strftime('%Y-%m-%d'),
                    'peso_primera_serie': float(primera_serie.peso),
                    'reps_primera_serie': primera_serie.repeticiones,
                    'peso_max': float(peso_max),
                    'peso_promedio': float(peso_promedio),
                    'repeticiones_total': repeticiones_total,
                    'series_total': len(registro.series),
                    'volumen_total': float(volumen_total),
                    'notas': registro.notas or '',
                    'series_detalle': [
                        {
                            'numero': serie.numero_serie,
                            'peso': float(serie.peso),
                            'repeticiones': serie.repeticiones,
                            'completada': serie.completada
                        } for serie in series_ordenadas
                    ]
                })
    
    ejercicio = Ejercicio.query.get_or_404(ejercicio_id)
    
    # Calcular estadísticas
    estadisticas = {}
    if datos:
        pesos_primera = [d['peso_primera_serie'] for d in datos]
        estadisticas = {
            'peso_actual': pesos_primera[-1] if pesos_primera else 0,
            'peso_inicial': pesos_primera[0] if pesos_primera else 0,
            'peso_maximo': max(pesos_primera) if pesos_primera else 0,
            'diferencia': (pesos_primera[-1] - pesos_primera[0]) if len(pesos_primera) > 1 else 0,
            'total_sesiones': len(datos),
            'volumen_promedio': sum(d['volumen_total'] for d in datos) / len(datos) if datos else 0
        }
    
    return {
        'ejercicio': ejercicio.nombre,
        'grupo_muscular': ejercicio.grupo_muscular,
        'datos': datos,
        'estadisticas': estadisticas,
        'periodo': f'Últimos {dias} días'
    }

@app.route('/agregar_ejercicio', methods=['POST'])
def agregar_ejercicio():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    nombre = request.form['nombre_ejercicio'].strip()
    grupo_muscular = request.form['grupo_muscular_ejercicio'].strip()
    descripcion = request.form.get('descripcion_ejercicio', '').strip()
    
    # Validar que no exista un ejercicio con el mismo nombre para este usuario
    ejercicio_existente = Ejercicio.query.filter(
        db.or_(
            db.and_(Ejercicio.nombre.ilike(nombre), Ejercicio.usuario_id == session['user_id']),
            db.and_(Ejercicio.nombre.ilike(nombre), Ejercicio.usuario_id.is_(None))
        )
    ).first()
    
    if ejercicio_existente:
        flash('Ya existe un ejercicio con ese nombre', 'error')
        return redirect(url_for('dashboard'))
    
    # Crear nuevo ejercicio personalizado
    nuevo_ejercicio = Ejercicio(
        nombre=nombre,
        grupo_muscular=grupo_muscular,
        descripcion=descripcion,
        usuario_id=session['user_id']
    )
    
    db.session.add(nuevo_ejercicio)
    db.session.commit()
    
    flash(f'Ejercicio "{nombre}" creado exitosamente!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/eliminar_ejercicio/<int:ejercicio_id>', methods=['POST'])
def eliminar_ejercicio(ejercicio_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    ejercicio = Ejercicio.query.get_or_404(ejercicio_id)
    
    # Verificar que el ejercicio pertenece al usuario
    if ejercicio.usuario_id != session['user_id']:
        flash('No tienes permiso para eliminar este ejercicio', 'error')
        return redirect(url_for('dashboard'))
    
    # Verificar si tiene registros asociados
    if ejercicio.registros:
        # No eliminar, solo desactivar para preservar historial
        ejercicio.activo = False
        db.session.commit()
        flash(f'Ejercicio "{ejercicio.nombre}" archivado (tiene historial de entrenamientos)', 'info')
    else:
        # Eliminar completamente si no tiene registros
        db.session.delete(ejercicio)
        db.session.commit()
        flash(f'Ejercicio "{ejercicio.nombre}" eliminado', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión', 'info')
    return redirect(url_for('index'))

def init_db():
    """Inicializar la base de datos con datos de ejemplo"""
    # Crear todas las tablas
    db.create_all()
    
    # Si hay una actualización de esquema, eliminar y recrear las tablas
    try:
        # Probar si la nueva estructura funciona
        SerieEjercicio.query.first()
        RegistroPeso.query.first()
        # Verificar que el modelo Ejercicio tiene el nuevo campo usuario_id
        ejercicio_test = Ejercicio.query.first()
        if ejercicio_test:
            _ = ejercicio_test.usuario_id  # Esto fallará si el campo no existe
    except Exception:
        # Si hay error, recrear las tablas
        print("Actualizando estructura de base de datos...")
        db.drop_all()
        db.create_all()
        print("Base de datos actualizada correctamente.")
    
    # Agregar ejercicios de ejemplo si no existen
    if Ejercicio.query.count() == 0:
        ejercicios_ejemplo = [
            #Ejercicios de Pecho
            Ejercicio(nombre='Press de Banca', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),
            Ejercicio(nombre='Press Inclinado con Mancuerna', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),
            Ejercicio(nombre='Máquina Contractora', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),
            Ejercicio(nombre='Press Pecho en Máquina', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),
            Ejercicio(nombre='Press de Banca Inclinado', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),
            Ejercicio(nombre='Press Pecho Superior en Máquina', grupo_muscular='Pecho', descripcion='Ejercicio para pecho'),

            #Ejercicios de Espalda
            Ejercicio(nombre='Remo con Barra', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Jalón al Pecho Agarre Neutro', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Jalón al Pecho Barra Amplia', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Remo en Máquina Baja', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Remo Gironda Espalda Alta', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Pull Over en Polea', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),
            Ejercicio(nombre='Remo Gironda', grupo_muscular='Espalda', descripcion='Ejercicio para espalda'),

            #Ejercicios de Triceps
            Ejercicio(nombre='Press Francés', grupo_muscular='Triceps', descripcion='Ejercicio para tríceps'),
            Ejercicio(nombre='Extensiones de Triceps con Barra Recta', grupo_muscular='Triceps', descripcion='Ejercicio para tríceps'),
            Ejercicio(nombre='Press Cerrado de Triceps', grupo_muscular='Triceps', descripcion='Ejercicio para tríceps'),
            Ejercicio(nombre='Extensiones de Triceps OH Unilateral', grupo_muscular='Triceps', descripcion='Ejercicio para tríceps'),
            Ejercicio(nombre='Fondos en Máquina', grupo_muscular='Triceps', descripcion='Ejercicio para tríceps'),

            #Ejercicios de Biceps
            Ejercicio(nombre='Curl de Bíceps', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl de Bíceps barra Z', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl de Bíceps recta', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl De Bíceps Banco Scott', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl Bayesian Polea', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl Martillo', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl Martillo Banco Scott', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),
            Ejercicio(nombre='Curl de Bíceps Banco Inclinado', grupo_muscular='Biceps', descripcion='Ejercicio para bíceps'),

            #Ejercicios de Hombro
            Ejercicio(nombre='Press Militar en Máquina', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),
            Ejercicio(nombre='Press Militar', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),
            Ejercicio(nombre='Elevaciones Laterales con Mancuerna', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),
            Ejercicio(nombre='Elevaciones Laterales en Polea Unilateral', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),
            Ejercicio(nombre='Remo al Cuello', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),
            Ejercicio(nombre='Hombro Posterior en Máquina', grupo_muscular='Hombros', descripcion='Ejercicio para hombros'),

            #Ejercicios de Piernas
            Ejercicio(nombre='Sentadillas en Smith', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'), 
            Ejercicio(nombre='Prensa 45º', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),  
            Ejercicio(nombre='Sentadillas en Barra Libre', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),  
            Ejercicio(nombre='Sentadilla Jaka', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),  
            Ejercicio(nombre='Extensiones de Cuadriceps Máquina', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),            
            Ejercicio(nombre='Extensiones de Femoral Máquina', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),   
            Ejercicio(nombre='Gemelos en Máquina', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),   
            Ejercicio(nombre='Peso Muerto Rumano', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'), 
            Ejercicio(nombre='Abductores en Máquina', grupo_muscular='Piernas', descripcion='Ejercicio para piernas'),

            #Ejercicios de Abdominales
            Ejercicio(nombre='Crunch en Máquina', grupo_muscular='Abdomen', descripcion='Ejercicio para abdomen'),   
        ]
        
        for ejercicio in ejercicios_ejemplo:
            db.session.add(ejercicio)
        
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
