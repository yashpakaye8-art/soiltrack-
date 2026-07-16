from flask import Flask, render_template, request, redirect, url_for, Response, flash, jsonify, session, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
import csv
import io
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'soiltrack2026secretkey')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
    f"{os.getenv('MYSQL_PASSWORD', '')}@"
    f"{os.getenv('MYSQL_HOST', 'localhost')}/"
    f"{os.getenv('MYSQL_DB', 'soiltrack_db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# UNIT LABELS for display on calculation page / Excel headers
PARAMETER_UNITS = {
    'nitrogen': 'kg/ha',
    'phosphorus': 'kg/ha',
    'potassium': 'kg/ha',
    'organic_carbon': '%',
    'ec': 'mS/cm',
    'sulphur': 'ppm',
    'boron': 'ppm',
    'zinc': 'ppm',
    'iron': 'ppm',
    'manganese': 'ppm',
    'copper': 'ppm',
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='staff')

class Sample(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(db.String(50), unique=True, nullable=False)
    village = db.Column(db.String(100), nullable=False)
    sample_type = db.Column(db.String(20))
    farmer_name = db.Column(db.String(100))
    collection_date = db.Column(db.String(20))

    # NEW: basic collection-time info
    phone_number = db.Column(db.String(20))
    address = db.Column(db.String(255))
    survey_number = db.Column(db.String(50))
    sample_source = db.Column(db.String(20))   # 'govt' or 'private'
    scheme = db.Column(db.String(150))         # only relevant when sample_source == 'govt'

    ph = db.Column(db.Float)
    ec = db.Column(db.Float)
    nitrogen = db.Column(db.Float)
    phosphorus = db.Column(db.Float)
    potassium = db.Column(db.Float)
    iron = db.Column(db.Float)
    manganese = db.Column(db.Float)
    copper = db.Column(db.Float)
    zinc = db.Column(db.Float)
    boron = db.Column(db.Float)
    organic_carbon = db.Column(db.Float)
    sulphur = db.Column(db.Float)
    # temperature / moisture REMOVED per request
    category = db.Column(db.String(20))
    notes = db.Column(db.String(200))
    observed_ec = db.Column(db.Float)
    ec_temperature = db.Column(db.Float)
    ec_comp_factor = db.Column(db.Float)
    n_burette_a = db.Column(db.Float)
    n_burette_b = db.Column(db.Float)
    abs_phosphorus = db.Column(db.Float)
    abs_potassium = db.Column(db.Float)
    abs_organic_carbon = db.Column(db.Float)
    abs_boron = db.Column(db.Float)
    abs_sulphur = db.Column(db.Float)
    abs_zinc = db.Column(db.Float)
    abs_iron = db.Column(db.Float)
    abs_manganese = db.Column(db.Float)
    abs_copper = db.Column(db.Float)

    # Analyzed by / Checked by / Approved by — for Soil Health Card
    analyzed_by = db.Column(db.String(100))
    checked_by = db.Column(db.String(100))
    approved_by = db.Column(db.String(100))

class DilutionFactor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parameter = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(100))
    factor = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(30))

def seed_dilution_factors():
    defaults = [
        ('phosphorus',     'Phosphorus (P)',      41.65,  'kg/ha'),
        ('potassium',      'Potassium (K)',        11.2,   'kg/ha'),
        ('organic_carbon', 'Organic Carbon (OC)', 2.78,   '%'),
        ('boron',          'Boron (B)',            5.36,   'ppm'),
        ('sulphur',        'Sulphur (S)',          541.0,  'ppm'),
        ('zinc',           'Zinc (Zn)',            18.8,   'ppm'),
        ('iron',           'Iron (Fe)',            72.6,   'ppm'),
        ('manganese',      'Manganese (Mn)',       39.87,  'ppm'),
        ('copper',         'Copper (Cu)',          32.98,  'ppm'),
    ]
    for param, label, factor, unit in defaults:
        exists = DilutionFactor.query.filter_by(parameter=param).first()
        if not exists:
            db.session.add(DilutionFactor(parameter=param, label=label, factor=factor, unit=unit))
    db.session.commit()

# ── Auth Helpers ──
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def staff_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'error')
            return redirect(url_for('login'))
        if session.get('role') not in ('staff', 'admin'):
            flash('You do not have permission to do that.', 'error')
            return redirect(url_for('all_samples'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'error')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Only Admin can do that.', 'error')
            return redirect(url_for('all_samples'))
        return f(*args, **kwargs)
    return decorated

EC_COMP_TABLE = {
    3.0:1.709,4.0:1.660,5.0:1.613,6.0:1.569,7.0:1.528,
    8.0:1.488,9.0:1.448,10.0:1.411,11.0:1.375,12.0:1.341,
    13.0:1.309,14.0:1.277,15.0:1.247,16.0:1.218,17.0:1.189,
    18.0:1.163,19.0:1.136,20.0:1.112,21.0:1.087,22.0:1.064,
    23.0:1.043,24.0:1.020,25.0:1.000,26.0:0.979,27.0:0.960,
    28.0:0.943,29.0:0.925,30.0:0.907,31.0:0.890,32.0:0.873,
    33.0:0.858,34.0:0.843,35.0:0.829,36.0:0.815,37.0:0.801,
    38.0:0.788,39.0:0.775,40.0:0.763,
}

def get_ec_comp_factor(temp):
    if not temp:
        return 1.0
    closest = min(EC_COMP_TABLE.keys(), key=lambda t: abs(t - temp))
    return EC_COMP_TABLE[closest]

def calculate_finals_from_raw(raw, factors):
    result = {}
    if raw.get('observed_ec') and raw.get('ec_temperature'):
        comp = get_ec_comp_factor(raw['ec_temperature'])
        result['ec'] = round(raw['observed_ec'] * comp, 4)
        result['ec_comp_factor'] = comp
    if raw.get('n_burette_a') is not None and raw.get('n_burette_b') is not None:
        result['nitrogen'] = round((raw['n_burette_a'] - raw['n_burette_b']) * 209.07, 2)
    abs_map = {
        'phosphorus':     'abs_phosphorus',
        'potassium':      'abs_potassium',
        'organic_carbon': 'abs_organic_carbon',
        'boron':          'abs_boron',
        'sulphur':        'abs_sulphur',
        'zinc':           'abs_zinc',
        'iron':           'abs_iron',
        'manganese':      'abs_manganese',
        'copper':         'abs_copper',
    }
    for param, abs_key in abs_map.items():
        if raw.get(abs_key) is not None:
            f = factors.get(param, 1.0)
            result[param] = round(raw[abs_key] * f, 4)
    return result

def get_factors_dict():
    factors = DilutionFactor.query.all()
    return {f.parameter: f.factor for f in factors}

def generate_sample_id(village):
    code = village[:3].upper()
    count = Sample.query.filter(Sample.sample_id.like(f"{code}%")).count()
    new_number = str(count + 1).zfill(2)
    return f"{code}{new_number}"

def get_category(ph, nitrogen, phosphorus, potassium):
    score = 0
    total = 0
    if ph:
        total += 1
        if 6.5 <= ph <= 7.5:
            score += 1
    if nitrogen:
        total += 1
        if nitrogen >= 280:
            score += 1
    if phosphorus:
        total += 1
        if phosphorus >= 11:
            score += 1
    if potassium:
        total += 1
        if potassium >= 110:
            score += 1
    if total == 0:
        return "Poor"
    ratio = score / total
    if ratio >= 0.75:
        return "Fertile"
    elif ratio >= 0.5:
        return "Moderate"
    else:
        return "Poor"

# ── Auth Routes ──
@app.route('/login', methods=['GET'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', error=None)

@app.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role_selected = request.form.get('role', 'staff')

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password, password):
        return render_template('login.html', error='Invalid username or password.')

    if user.role != role_selected:
        return render_template('login.html', error=f'This account is registered as "{user.role}", not "{role_selected}". Please select the correct role.')

    session['user_id'] = user.id
    session['username'] = user.username
    session['fullname'] = user.fullname
    session['role'] = user.role
    flash(f'Welcome back, {user.fullname or user.username}!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET'])
def register():
    list(get_flashed_messages())  # clear any stray flash messages from previous redirects
    admin_exists = User.query.filter_by(role='admin').first() is not None
    return render_template('register.html', error=None, admin_exists=admin_exists)

@app.route('/register', methods=['POST'])
def register_post():
    fullname = request.form.get('fullname', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    role = request.form.get('role', 'staff')
    if role not in ('staff', 'admin'):
        role = 'staff'

    admin_exists = User.query.filter_by(role='admin').first() is not None

    # Block creating a second admin even if someone bypasses the hidden UI pill
    if role == 'admin' and admin_exists:
        return render_template('register.html', error='An Admin account already exists for this system. Please register as Lab Staff instead.', admin_exists=admin_exists)

    if not username or not password:
        return render_template('register.html', error='Username and password are required.', admin_exists=admin_exists)

    if password != confirm_password:
        return render_template('register.html', error='Passwords do not match. Please try again.', admin_exists=admin_exists)

    existing = User.query.filter_by(username=username).first()
    if existing:
        return render_template('register.html', error='Username already taken. Please choose another.', admin_exists=admin_exists)

    new_user = User(
        fullname=fullname,
        username=username,
        password=generate_password_hash(password),
        role=role
    )
    db.session.add(new_user)
    db.session.commit()
    flash('Account created successfully! Please login.', 'success')
    return redirect(url_for('login'))

def seed_admin_account():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        db.session.add(User(
            fullname='Administrator',
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin'
        ))
        db.session.commit()

# ── Dashboard ──
@app.route('/')
@login_required
def dashboard():
    total = Sample.query.count()
    fertile = Sample.query.filter_by(category='Fertile').count()
    moderate = Sample.query.filter_by(category='Moderate').count()
    poor = Sample.query.filter_by(category='Poor').count()
    recent = Sample.query.order_by(Sample.id.desc()).limit(5).all()
    return render_template('dashboard.html',
        total=total, fertile=fertile,
        moderate=moderate, poor=poor, recent=recent)

# ── Samples ──
@app.route('/samples')
@login_required
def all_samples():
    samples = Sample.query.all()
    return render_template('samples.html', samples=samples)

@app.route('/add')
@staff_or_admin_required
def add_sample():
    return render_template('add_sample.html')

@app.route('/add', methods=['POST'])
@staff_or_admin_required
def save_sample():
    """
    Collection-time registration ONLY.
    No chemistry parameters here anymore — those are entered later
    via the Lab Calculation wizard once the sample is actually tested.
    """
    village = request.form.get('village')
    sample_source = request.form.get('sample_source', 'private')
    scheme = request.form.get('scheme') if sample_source == 'govt' else None

    new_sample = Sample(
        sample_id       = generate_sample_id(village),
        village         = village,
        sample_type     = request.form.get('sample_type'),
        farmer_name     = request.form.get('farmer_name'),
        collection_date = request.form.get('collection_date'),
        phone_number    = request.form.get('phone_number'),
        address         = request.form.get('address'),
        survey_number   = request.form.get('survey_number'),
        sample_source   = sample_source,
        scheme          = scheme,
        notes           = request.form.get('notes'),
        category        = None,  # unknown until lab calculation is done
    )
    db.session.add(new_sample)
    db.session.commit()
    flash(f'Sample {new_sample.sample_id} registered. Parameters can be added later via Lab Calculation.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/sample/<int:id>')
@login_required
def sample_detail(id):
    sample = db.session.get(Sample, id)
    if not sample:
        return redirect(url_for('all_samples'))
    return render_template('sample_detail.html', sample=sample)

@app.route('/edit/<int:id>')
@staff_or_admin_required
def edit_sample(id):
    sample = db.session.get(Sample, id)
    return render_template('edit_sample.html', sample=sample)

@app.route('/edit/<int:id>', methods=['POST'])
@staff_or_admin_required
def update_sample(id):
    """
    Edits basic collection-time info only (village, farmer, phone,
    address, survey number, scheme, notes). Chemistry parameters are
    edited via the Lab Calculation wizard / api_update_sample instead.
    """
    sample = db.session.get(Sample, id)
    sample_source = request.form.get('sample_source', sample.sample_source or 'private')
    scheme = request.form.get('scheme') if sample_source == 'govt' else None

    sample.village         = request.form.get('village')
    sample.sample_type     = request.form.get('sample_type')
    sample.farmer_name     = request.form.get('farmer_name')
    sample.collection_date = request.form.get('collection_date')
    sample.phone_number    = request.form.get('phone_number')
    sample.address         = request.form.get('address')
    sample.survey_number   = request.form.get('survey_number')
    sample.sample_source   = sample_source
    sample.scheme          = scheme
    sample.notes           = request.form.get('notes')
    db.session.commit()
    return redirect(url_for('sample_detail', id=sample.id))

@app.route('/delete/<int:id>')
@admin_required
def delete_sample(id):
    sample = db.session.get(Sample, id)
    db.session.delete(sample)
    db.session.commit()
    return redirect(url_for('all_samples'))

# ── Export ──
def _export_headers():
    return [
        'Sample ID', 'Village', 'Type', 'Farmer', 'Phone Number', 'Address',
        'Survey Number', 'Sample Source', 'Scheme', 'Date',
        'pH', f"EC ({PARAMETER_UNITS['ec']})", f"OC ({PARAMETER_UNITS['organic_carbon']})",
        f"Nitrogen ({PARAMETER_UNITS['nitrogen']})",
        f"Phosphorus ({PARAMETER_UNITS['phosphorus']})",
        f"Potassium ({PARAMETER_UNITS['potassium']})",
        f"Iron ({PARAMETER_UNITS['iron']})",
        f"Manganese ({PARAMETER_UNITS['manganese']})",
        f"Copper ({PARAMETER_UNITS['copper']})",
        f"Zinc ({PARAMETER_UNITS['zinc']})",
        f"Boron ({PARAMETER_UNITS['boron']})",
        f"Sulphur ({PARAMETER_UNITS['sulphur']})",
        'Category', 'Notes',
        'Observed EC', 'EC Temp', 'EC Comp Factor',
        'N Burette A', 'N Burette B',
        'Abs P', 'Abs K', 'Abs OC', 'Abs B', 'Abs S',
        'Abs Zn', 'Abs Fe', 'Abs Mn', 'Abs Cu'
    ]
    # NOTE: Temperature / Moisture columns removed per request

def _export_row(s):
    return [
        s.sample_id, s.village, s.sample_type, s.farmer_name,
        s.phone_number, s.address, s.survey_number,
        s.sample_source, s.scheme, s.collection_date,
        s.ph, s.ec, s.organic_carbon,
        s.nitrogen, s.phosphorus, s.potassium,
        s.iron, s.manganese, s.copper, s.zinc, s.boron, s.sulphur,
        s.category, s.notes,
        s.observed_ec, s.ec_temperature, s.ec_comp_factor,
        s.n_burette_a, s.n_burette_b,
        s.abs_phosphorus, s.abs_potassium, s.abs_organic_carbon,
        s.abs_boron, s.abs_sulphur, s.abs_zinc,
        s.abs_iron, s.abs_manganese, s.abs_copper
    ]

@app.route('/export')
@login_required
def export_excel():
    samples = Sample.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_export_headers())
    for s in samples:
        writer.writerow(_export_row(s))
    output.seek(0)
    return Response(output, mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=soiltrack_samples.csv"})

@app.route('/export-selected')
@login_required
def export_selected():
    ids_param = request.args.get('ids', '')
    if not ids_param:
        return redirect(url_for('all_samples'))
    ids = [int(i) for i in ids_param.split(',') if i.isdigit()]
    samples = Sample.query.filter(Sample.id.in_(ids)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_export_headers())
    for s in samples:
        writer.writerow(_export_row(s))
    output.seek(0)
    filename = f'soiltrack_selected_{len(samples)}_samples.csv'
    return Response(output, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment;filename={filename}'})

# ── Recalculate ──
@app.route('/recalculate')
@admin_required
def recalculate():
    samples = Sample.query.all()
    factors = get_factors_dict()
    count = 0
    for s in samples:
        raw = {
            'observed_ec': s.observed_ec, 'ec_temperature': s.ec_temperature,
            'n_burette_a': s.n_burette_a, 'n_burette_b': s.n_burette_b,
            'abs_phosphorus': s.abs_phosphorus, 'abs_potassium': s.abs_potassium,
            'abs_organic_carbon': s.abs_organic_carbon, 'abs_boron': s.abs_boron,
            'abs_sulphur': s.abs_sulphur, 'abs_zinc': s.abs_zinc,
            'abs_iron': s.abs_iron, 'abs_manganese': s.abs_manganese,
            'abs_copper': s.abs_copper,
        }
        calc = calculate_finals_from_raw(raw, factors)
        if calc.get('ec'):             s.ec = calc['ec']
        if calc.get('nitrogen'):       s.nitrogen = calc['nitrogen']
        if calc.get('phosphorus'):     s.phosphorus = calc['phosphorus']
        if calc.get('potassium'):      s.potassium = calc['potassium']
        if calc.get('organic_carbon'): s.organic_carbon = calc['organic_carbon']
        if calc.get('boron'):          s.boron = calc['boron']
        if calc.get('sulphur'):        s.sulphur = calc['sulphur']
        if calc.get('zinc'):           s.zinc = calc['zinc']
        if calc.get('iron'):           s.iron = calc['iron']
        if calc.get('manganese'):      s.manganese = calc['manganese']
        if calc.get('copper'):         s.copper = calc['copper']
        s.category = get_category(s.ph, s.nitrogen, s.phosphorus, s.potassium)
        count += 1
    db.session.commit()
    return f'✅ Recalculated {count} samples! <a href="/">Go to Dashboard</a>'

# ── Dilution Factors ──
@app.route('/dilution-factors')
@staff_or_admin_required
def dilution_factors():
    factors = DilutionFactor.query.all()
    return render_template('dilution_factors.html', factors=factors)

@app.route('/dilution-factors/update', methods=['POST'])
@admin_required
def update_dilution_factors():
    factors = DilutionFactor.query.all()
    for f in factors:
        new_value = request.form.get(f.parameter, type=float)
        if new_value is not None:
            f.factor = new_value
    db.session.commit()
    flash('✅ Dilution factors updated successfully!', 'success')
    return redirect(url_for('dilution_factors'))

# ── Lab Calculation Wizard ──
@app.route('/lab-calculation')
@staff_or_admin_required
def lab_calculation():
    return render_template('lab_calculation.html', units=PARAMETER_UNITS)

# ── API Routes ──
@app.route('/api/factors')
def api_factors():
    return jsonify(get_factors_dict())

@app.route('/api/units')
def api_units():
    return jsonify(PARAMETER_UNITS)

# ── UPDATED: returns ALL fields for auto-fill ──
@app.route('/api/sample-by-id/<sample_id>')
def api_sample_by_id(sample_id):
    sample = Sample.query.filter_by(sample_id=sample_id).first()
    if not sample:
        return jsonify({'found': False})
    return jsonify({
        'found': True,
        # Step 1
        'farmer_name':     sample.farmer_name,
        'village':         sample.village,
        'sample_type':     sample.sample_type,
        'collection_date': sample.collection_date,
        'phone_number':    sample.phone_number,
        'address':         sample.address,
        'survey_number':   sample.survey_number,
        'sample_source':   sample.sample_source,
        'scheme':          sample.scheme,
        # Step 2
        'ph':              sample.ph,
        'observed_ec':     sample.observed_ec,
        'ec_temperature':  sample.ec_temperature,
        'ec':              sample.ec,
        # Step 3
        'n_burette_a':     sample.n_burette_a,
        'n_burette_b':     sample.n_burette_b,
        'nitrogen':        sample.nitrogen,
        # Step 4
        'abs_phosphorus':  sample.abs_phosphorus,
        'phosphorus':      sample.phosphorus,
        'abs_potassium':   sample.abs_potassium,
        'potassium':       sample.potassium,
        # Step 5
        'abs_organic_carbon': sample.abs_organic_carbon,
        'organic_carbon':     sample.organic_carbon,
        'abs_boron':          sample.abs_boron,
        'boron':              sample.boron,
        'abs_sulphur':        sample.abs_sulphur,
        'sulphur':            sample.sulphur,
        # Step 6
        'abs_zinc':        sample.abs_zinc,
        'zinc':            sample.zinc,
        'abs_iron':        sample.abs_iron,
        'iron':            sample.iron,
        'abs_manganese':   sample.abs_manganese,
        'manganese':       sample.manganese,
        'abs_copper':      sample.abs_copper,
        'copper':          sample.copper,
        # Step 7
        'notes':           sample.notes,
        # Sign-off
        'analyzed_by':     sample.analyzed_by,
        'checked_by':      sample.checked_by,
        'approved_by':     sample.approved_by,
    })

@app.route('/api/save-sample', methods=['POST'])
def api_save_sample():
    """
    Kept for the Lab Calculation wizard's own save path
    (chemistry parameters only — basic info is set at /add time).
    """
    data = request.get_json()
    sample_id = data.get('sample_id')
    sample = Sample.query.filter_by(sample_id=sample_id).first() if sample_id else None

    ph = data.get('ph')
    nitrogen = data.get('nitrogen')
    phosphorus = data.get('phosphorus')
    potassium = data.get('potassium')

    if not sample:
        # Fallback: create a bare sample if none exists (shouldn't normally happen
        # since registration now happens via /add first)
        village = data.get('village', 'Unknown')
        sample = Sample(sample_id=generate_sample_id(village), village=village)
        db.session.add(sample)

    sample.ph                 = ph
    sample.ec                 = data.get('ec')
    sample.nitrogen           = nitrogen
    sample.phosphorus         = phosphorus
    sample.potassium          = potassium
    sample.iron               = data.get('iron')
    sample.manganese          = data.get('manganese')
    sample.copper             = data.get('copper')
    sample.zinc               = data.get('zinc')
    sample.boron              = data.get('boron')
    sample.organic_carbon     = data.get('organic_carbon')
    sample.sulphur             = data.get('sulphur')
    sample.observed_ec        = data.get('observed_ec')
    sample.ec_temperature     = data.get('ec_temperature')
    sample.n_burette_a        = data.get('n_burette_a')
    sample.n_burette_b        = data.get('n_burette_b')
    sample.abs_phosphorus     = data.get('abs_phosphorus')
    sample.abs_potassium      = data.get('abs_potassium')
    sample.abs_organic_carbon = data.get('abs_organic_carbon')
    sample.abs_boron          = data.get('abs_boron')
    sample.abs_sulphur        = data.get('abs_sulphur')
    sample.abs_zinc           = data.get('abs_zinc')
    sample.abs_iron           = data.get('abs_iron')
    sample.abs_manganese      = data.get('abs_manganese')
    sample.abs_copper         = data.get('abs_copper')
    sample.notes              = data.get('notes') or sample.notes
    sample.analyzed_by        = data.get('analyzed_by') or sample.analyzed_by
    sample.checked_by         = data.get('checked_by') or sample.checked_by
    sample.approved_by        = data.get('approved_by') or sample.approved_by
    sample.category = get_category(ph, nitrogen, phosphorus, potassium)
    db.session.commit()
    return jsonify({'success': True, 'sample_id': sample.sample_id})

@app.route('/api/update-sample/<sample_id>', methods=['POST'])
def api_update_sample(sample_id):
    sample = Sample.query.filter_by(sample_id=sample_id).first()
    if not sample:
        return jsonify({'success': False, 'error': 'Sample not found'})
    data = request.get_json()
    sample.ph              = data.get('ph') or sample.ph
    sample.ec              = data.get('ec') or sample.ec
    sample.nitrogen        = data.get('nitrogen') or sample.nitrogen
    sample.phosphorus      = data.get('phosphorus') or sample.phosphorus
    sample.potassium       = data.get('potassium') or sample.potassium
    sample.iron            = data.get('iron') or sample.iron
    sample.manganese       = data.get('manganese') or sample.manganese
    sample.copper          = data.get('copper') or sample.copper
    sample.zinc            = data.get('zinc') or sample.zinc
    sample.boron           = data.get('boron') or sample.boron
    sample.organic_carbon  = data.get('organic_carbon') or sample.organic_carbon
    sample.sulphur         = data.get('sulphur') or sample.sulphur
    sample.observed_ec        = data.get('observed_ec') or sample.observed_ec
    sample.ec_temperature     = data.get('ec_temperature') or sample.ec_temperature
    sample.n_burette_a        = data.get('n_burette_a') or sample.n_burette_a
    sample.n_burette_b        = data.get('n_burette_b') or sample.n_burette_b
    sample.abs_phosphorus     = data.get('abs_phosphorus') or sample.abs_phosphorus
    sample.abs_potassium      = data.get('abs_potassium') or sample.abs_potassium
    sample.abs_organic_carbon = data.get('abs_organic_carbon') or sample.abs_organic_carbon
    sample.abs_boron          = data.get('abs_boron') or sample.abs_boron
    sample.abs_sulphur        = data.get('abs_sulphur') or sample.abs_sulphur
    sample.abs_zinc           = data.get('abs_zinc') or sample.abs_zinc
    sample.abs_iron           = data.get('abs_iron') or sample.abs_iron
    sample.abs_manganese      = data.get('abs_manganese') or sample.abs_manganese
    sample.abs_copper         = data.get('abs_copper') or sample.abs_copper
    sample.farmer_name        = data.get('farmer_name') or sample.farmer_name
    sample.village            = data.get('village') or sample.village
    sample.sample_type        = data.get('sample_type') or sample.sample_type
    sample.collection_date    = data.get('collection_date') or sample.collection_date
    sample.phone_number       = data.get('phone_number') or sample.phone_number
    sample.address            = data.get('address') or sample.address
    sample.survey_number      = data.get('survey_number') or sample.survey_number
    sample.sample_source      = data.get('sample_source') or sample.sample_source
    sample.scheme             = data.get('scheme') or sample.scheme
    sample.notes              = data.get('notes') or sample.notes
    sample.analyzed_by        = data.get('analyzed_by') or sample.analyzed_by
    sample.checked_by         = data.get('checked_by') or sample.checked_by
    sample.approved_by        = data.get('approved_by') or sample.approved_by
    sample.category = get_category(sample.ph, sample.nitrogen, sample.phosphorus, sample.potassium)
    db.session.commit()
    return jsonify({'success': True, 'sample_id': sample.sample_id})

# ── Soil Health Card ──
@app.route('/soil-health-card/<int:id>')
@login_required
def soil_health_card(id):
    sample = db.session.get(Sample, id)
    if not sample:
        return redirect(url_for('all_samples'))
    return render_template('soil_health_card.html', sample=sample, units=PARAMETER_UNITS)

# ── Users ──
@app.route('/users')
@admin_required
def users():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@app.route('/delete_user/<int:id>')
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('users'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_dilution_factors()
        seed_admin_account()
    app.run(debug=True)