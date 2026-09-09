import os
import io
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file, g
)
from werkzeug.security import generate_password_hash, check_password_hash

from models import get_db, init_db, seed_default_sections, log_audit, DEFAULT_PASSWORD, ADMIN_EMAIL
from export_docx import generate_docx

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'hsa-minit-mesyuarat-2026-dev')
app.config['STORAGE_DIR'] = os.environ.get('STORAGE_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage'))
os.makedirs(app.config['STORAGE_DIR'], exist_ok=True)


@app.route('/healthz')
def healthz():
    return 'OK', 200

init_db()

HARI_MAP = {
    'Monday': 'Isnin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
    'Thursday': 'Khamis', 'Friday': 'Jumaat', 'Saturday': 'Sabtu', 'Sunday': 'Ahad'
}

BULAN_MAP = {
    1: 'Januari', 2: 'Februari', 3: 'Mac', 4: 'April',
    5: 'Mei', 6: 'Jun', 7: 'Julai', 8: 'Ogos',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Disember'
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('peranan') not in ('admin', 'superadmin'):
            flash('Akses ditolak. Hanya pentadbir sahaja.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('peranan') != 'superadmin':
            flash('Akses ditolak. Hanya pentadbir utama sahaja.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def get_user_storage(user_id):
    path = os.path.join(app.config['STORAGE_DIR'], str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def format_tarikh_bm(tarikh_str):
    if not tarikh_str:
        return ''
    try:
        dt = datetime.strptime(tarikh_str, '%Y-%m-%d')
        hari = HARI_MAP.get(dt.strftime('%A'), '')
        bulan = BULAN_MAP.get(dt.month, '')
        return f"{dt.day} {bulan} {dt.year} ({hari})"
    except ValueError:
        return tarikh_str


def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '')


@app.before_request
def before_request():
    if 'user_id' in session:
        db = get_db()
        g.user = db.execute("SELECT * FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()
        db.close()
    else:
        g.user = None


# ── Auth ──

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM pengguna WHERE email = ?", (email,)).fetchone()
        db.close()

        if not user:
            flash('Emel atau kata laluan tidak sah.', 'error')
            return render_template('login.html')

        if not check_password_hash(user['password_hash'], password):
            log_audit(None, email, 'log_masuk_gagal', 'Kata laluan salah', get_client_ip())
            flash('Emel atau kata laluan tidak sah.', 'error')
            return render_template('login.html')

        if user['status'] == 'menunggu':
            flash('Akaun anda masih menunggu kelulusan pentadbir.', 'error')
            return render_template('login.html')

        if user['status'] == 'ditolak':
            flash('Pendaftaran anda telah ditolak. Sila hubungi pentadbir.', 'error')
            return render_template('login.html')

        session['user_id'] = user['id']
        session['email'] = user['email']
        session['nama'] = user['nama']
        session['peranan'] = user['peranan']
        log_audit(user['id'], user['email'], 'log_masuk', 'Berjaya', get_client_ip())
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/daftar', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        nama = request.form['nama'].strip()
        jawatan = request.form.get('jawatan', '').strip()
        jabatan = request.form.get('jabatan', '').strip()

        if not email or not nama:
            flash('Sila isi semua ruangan wajib.', 'error')
            return render_template('register.html')

        if not email.endswith('@moh.gov.my'):
            flash('Hanya emel @moh.gov.my dibenarkan.', 'error')
            return render_template('register.html')

        db = get_db()
        existing = db.execute("SELECT id FROM pengguna WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            flash('Emel sudah berdaftar.', 'error')
            return render_template('register.html')

        db.execute(
            """INSERT INTO pengguna (email, password_hash, nama, jawatan, jabatan, peranan, status)
               VALUES (?,?,?,?,?,?,?)""",
            (email, generate_password_hash(DEFAULT_PASSWORD), nama, jawatan, jabatan,
             'pengguna', 'menunggu')
        )
        db.commit()
        db.close()
        log_audit(None, email, 'pendaftaran', f'Pendaftaran baru: {nama}', get_client_ip())
        flash(f'Pendaftaran berjaya! Kata laluan lalai: {DEFAULT_PASSWORD}. Akaun anda perlu diluluskan oleh pentadbir sebelum boleh log masuk.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/tukar-kata-laluan', methods=['GET', 'POST'])
@login_required
def tukar_kata_laluan():
    if request.method == 'POST':
        current = request.form['current_password']
        new_pw = request.form['new_password']
        confirm = request.form['confirm_password']
        db = get_db()
        user = db.execute("SELECT * FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()

        if not check_password_hash(user['password_hash'], current):
            db.close()
            flash('Kata laluan semasa tidak betul.', 'error')
            return render_template('tukar_password.html')

        if new_pw != confirm:
            db.close()
            flash('Kata laluan baru tidak sepadan.', 'error')
            return render_template('tukar_password.html')

        if len(new_pw) < 6:
            db.close()
            flash('Kata laluan mestilah sekurang-kurangnya 6 aksara.', 'error')
            return render_template('tukar_password.html')

        db.execute("UPDATE pengguna SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_pw), session['user_id']))
        db.commit()
        db.close()
        log_audit(session['user_id'], session['email'], 'tukar_kata_laluan', '', get_client_ip())
        flash('Kata laluan berjaya ditukar.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('tukar_password.html')


@app.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    db = get_db()
    user = db.execute("SELECT * FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()

    if request.method == 'POST':
        jawatan = request.form.get('jawatan', '').strip()
        jabatan = request.form.get('jabatan', '').strip()
        db.execute("UPDATE pengguna SET jawatan = ?, jabatan = ? WHERE id = ?",
                   (jawatan, jabatan, session['user_id']))
        db.commit()
        db.close()
        log_audit(session['user_id'], session['email'], 'kemaskini_profil',
                  f'Jawatan: {jawatan}, Jabatan: {jabatan}', get_client_ip())
        flash('Profil berjaya dikemaskini.', 'success')
        return redirect(url_for('profil'))

    db.close()
    return render_template('profil.html', user=user)


@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_audit(session.get('user_id'), session.get('email'), 'log_keluar', '', get_client_ip())
    session.clear()
    return redirect(url_for('login'))


# ── Admin ──

@app.route('/admin/pengguna')
@superadmin_required
def admin_pengguna():
    db = get_db()
    users = db.execute("SELECT * FROM pengguna ORDER BY status, created_at DESC").fetchall()
    db.close()
    return render_template('admin_pengguna.html', users=users)


@app.route('/admin/pengguna/<int:uid>/lulus', methods=['POST'])
@superadmin_required
def admin_lulus(uid):
    db = get_db()
    db.execute("UPDATE pengguna SET status = 'aktif', approved_by = ?, approved_at = datetime('now','localtime') WHERE id = ?",
               (session['user_id'], uid))
    user = db.execute("SELECT email, nama FROM pengguna WHERE id = ?", (uid,)).fetchone()
    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'lulus_pengguna',
              f"Meluluskan: {user['nama']} ({user['email']})", get_client_ip())
    flash(f"Pengguna {user['nama']} telah diluluskan.", 'success')
    return redirect(url_for('admin_pengguna'))


@app.route('/admin/pengguna/<int:uid>/tolak', methods=['POST'])
@superadmin_required
def admin_tolak(uid):
    db = get_db()
    user = db.execute("SELECT email, nama FROM pengguna WHERE id = ?", (uid,)).fetchone()
    db.execute("UPDATE pengguna SET status = 'ditolak' WHERE id = ?", (uid,))
    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'tolak_pengguna',
              f"Menolak: {user['nama']} ({user['email']})", get_client_ip())
    flash(f"Pendaftaran {user['nama']} telah ditolak.", 'success')
    return redirect(url_for('admin_pengguna'))


@app.route('/admin/pengguna/<int:uid>/reset', methods=['POST'])
@superadmin_required
def admin_reset_password(uid):
    db = get_db()
    user = db.execute("SELECT email, nama FROM pengguna WHERE id = ?", (uid,)).fetchone()
    db.execute("UPDATE pengguna SET password_hash = ? WHERE id = ?",
               (generate_password_hash(DEFAULT_PASSWORD), uid))
    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'reset_kata_laluan',
              f"Reset untuk: {user['nama']} ({user['email']})", get_client_ip())
    flash(f"Kata laluan {user['nama']} telah direset ke lalai.", 'success')
    return redirect(url_for('admin_pengguna'))


@app.route('/admin/pengguna/<int:uid>/peranan', methods=['POST'])
@superadmin_required
def admin_set_peranan(uid):
    peranan = request.form.get('peranan', 'pengguna')
    if peranan not in ('pengguna', 'admin'):
        flash('Peranan tidak sah.', 'error')
        return redirect(url_for('admin_pengguna'))
    db = get_db()
    user = db.execute("SELECT email, nama, peranan FROM pengguna WHERE id = ?", (uid,)).fetchone()
    if user and user['peranan'] == 'superadmin':
        db.close()
        flash('Tidak boleh menukar peranan pentadbir utama.', 'error')
        return redirect(url_for('admin_pengguna'))
    db.execute("UPDATE pengguna SET peranan = ? WHERE id = ?", (peranan, uid))
    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'tukar_peranan',
              f"{user['nama']} ({user['email']}): {user['peranan']} -> {peranan}", get_client_ip())
    flash(f"Peranan {user['nama']} ditukar kepada {peranan}.", 'success')
    return redirect(url_for('admin_pengguna'))


@app.route('/admin/audit')
@superadmin_required
def admin_audit():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    total = db.execute("SELECT COUNT(*) FROM audit_trail").fetchone()[0]
    logs = db.execute(
        "SELECT * FROM audit_trail ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    db.close()
    total_pages = (total + per_page - 1) // per_page
    return render_template('admin_audit.html', logs=logs, page=page, total_pages=total_pages)


# ── Dashboard ──

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    minit_list = db.execute(
        "SELECT * FROM minit WHERE user_id = ? ORDER BY updated_at DESC",
        (session['user_id'],)
    ).fetchall()
    db.close()
    return render_template('dashboard.html', minit_list=minit_list)


# ── Minit CRUD ──

@app.route('/minit/baru', methods=['GET', 'POST'])
@login_required
def minit_baru():
    if request.method == 'POST':
        tajuk = request.form['tajuk_mesyuarat'].strip()
        bil = request.form['bil'].strip()
        hospital = request.form.get('hospital', 'HOSPITAL SHAH ALAM').strip()
        tarikh = request.form.get('tarikh', '')
        masa_mula = request.form.get('masa_mula', '')
        masa_tamat = request.form.get('masa_tamat', '')
        tempat = request.form.get('tempat', 'Bilik Persidangan, Aras 2').strip()

        hari = ''
        if tarikh:
            try:
                dt = datetime.strptime(tarikh, '%Y-%m-%d')
                hari = HARI_MAP.get(dt.strftime('%A'), '')
            except ValueError:
                pass

        db = get_db()
        cursor = db.execute(
            """INSERT INTO minit (user_id, tajuk_mesyuarat, bil, hospital, tarikh, hari,
               masa_mula, masa_tamat, tempat) VALUES (?,?,?,?,?,?,?,?,?)""",
            (session['user_id'], tajuk, bil, hospital, tarikh, hari, masa_mula, masa_tamat, tempat)
        )
        minit_id = cursor.lastrowid
        db.commit()
        db.close()

        seed_default_sections(minit_id)
        log_audit(session['user_id'], session['email'], 'cipta_minit',
                  f"Minit: {tajuk} Bil. {bil}", get_client_ip())
        return redirect(url_for('minit_edit', minit_id=minit_id))

    return render_template('minit_baru.html')


@app.route('/minit/<int:minit_id>/edit')
@login_required
def minit_edit(minit_id):
    db = get_db()
    minit = db.execute("SELECT * FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if not minit:
        db.close()
        flash('Minit tidak dijumpai.', 'error')
        return redirect(url_for('dashboard'))

    kehadiran = db.execute(
        "SELECT * FROM kehadiran WHERE minit_id = ? ORDER BY kategori, urutan", (minit_id,)
    ).fetchall()

    seksyen_rows = db.execute(
        "SELECT * FROM seksyen WHERE minit_id = ? ORDER BY urutan", (minit_id,)
    ).fetchall()

    seksyen = []
    for s in seksyen_rows:
        perkara = db.execute(
            "SELECT * FROM perkara WHERE seksyen_id = ? ORDER BY urutan", (s['id'],)
        ).fetchall()
        seksyen.append({'seksyen': s, 'perkara': perkara})

    kakitangan = db.execute(
        "SELECT * FROM kakitangan WHERE aktif = 1 ORDER BY jabatan, nama"
    ).fetchall()

    maklumbalas = db.execute(
        "SELECT * FROM maklumbalas WHERE minit_id = ? ORDER BY bil", (minit_id,)
    ).fetchall()

    db.close()

    kehadiran_dict = {
        'hadir': [k for k in kehadiran if k['kategori'] == 'hadir'],
        'tidak_hadir': [k for k in kehadiran if k['kategori'] == 'tidak_hadir'],
        'turut_hadir': [k for k in kehadiran if k['kategori'] == 'turut_hadir'],
        'urus_setia': [k for k in kehadiran if k['kategori'] == 'urus_setia'],
    }

    return render_template('minit_form.html',
                           minit=minit, kehadiran=kehadiran_dict,
                           seksyen=seksyen, kakitangan=kakitangan,
                           maklumbalas=maklumbalas)


@app.route('/minit/<int:minit_id>/simpan', methods=['POST'])
@login_required
def minit_simpan(minit_id):
    db = get_db()
    minit = db.execute("SELECT * FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if not minit:
        db.close()
        return jsonify({'error': 'Minit tidak dijumpai'}), 404

    data = request.get_json()

    tarikh = data.get('tarikh', minit['tarikh'])
    hari = ''
    if tarikh:
        try:
            dt = datetime.strptime(tarikh, '%Y-%m-%d')
            hari = HARI_MAP.get(dt.strftime('%A'), '')
        except ValueError:
            pass

    new_status = data.get('status', minit['status'])

    db.execute("""UPDATE minit SET tajuk_mesyuarat=?, bil=?, hospital=?, tarikh=?, hari=?,
                  masa_mula=?, masa_tamat=?, tempat=?, status=?,
                  updated_at=datetime('now','localtime') WHERE id=?""",
               (data.get('tajuk_mesyuarat', minit['tajuk_mesyuarat']),
                data.get('bil', minit['bil']),
                data.get('hospital', minit['hospital']),
                tarikh, hari,
                data.get('masa_mula', minit['masa_mula']),
                data.get('masa_tamat', minit['masa_tamat']),
                data.get('tempat', minit['tempat']),
                new_status,
                minit_id))

    if 'kehadiran' in data:
        db.execute("DELETE FROM kehadiran WHERE minit_id = ?", (minit_id,))
        for kat, items in data['kehadiran'].items():
            for i, item in enumerate(items):
                db.execute("""INSERT INTO kehadiran
                    (minit_id, kakitangan_id, nama, jawatan, kategori, is_pengerusi, is_pencatat,
                     wakil_nama, wakil_jawatan, urutan)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (minit_id, item.get('kakitangan_id'), item.get('nama', ''),
                     item.get('jawatan', ''), kat,
                     1 if item.get('is_pengerusi') else 0,
                     1 if item.get('is_pencatat') else 0,
                     item.get('wakil_nama', ''), item.get('wakil_jawatan', ''), i))

    if 'seksyen' in data:
        old_seksyen = db.execute("SELECT id FROM seksyen WHERE minit_id = ?", (minit_id,)).fetchall()
        for s in old_seksyen:
            db.execute("DELETE FROM perkara WHERE seksyen_id = ?", (s['id'],))
        db.execute("DELETE FROM seksyen WHERE minit_id = ?", (minit_id,))

        for i, sek in enumerate(data['seksyen']):
            cursor = db.execute(
                "INSERT INTO seksyen (minit_id, nombor_romawi, tajuk, urutan) VALUES (?,?,?,?)",
                (minit_id, sek.get('nombor_romawi', ''), sek.get('tajuk', ''), i)
            )
            seksyen_id = cursor.lastrowid
            for j, p in enumerate(sek.get('perkara', [])):
                db.execute(
                    """INSERT INTO perkara (seksyen_id, nombor, kandungan, tindakan, pegawai,
                       status_tindakan, urutan) VALUES (?,?,?,?,?,?,?)""",
                    (seksyen_id, p.get('nombor', j + 1), p.get('kandungan', ''),
                     p.get('tindakan', ''), p.get('pegawai', ''),
                     p.get('status_tindakan', 'baru'), j)
                )

    if 'maklumbalas' in data:
        db.execute("DELETE FROM maklumbalas WHERE minit_id = ?", (minit_id,))
        for i, mb in enumerate(data['maklumbalas']):
            db.execute(
                """INSERT INTO maklumbalas (minit_id, bil, no_rujukan, perkara,
                   tindakan_makluman_1, tindakan_makluman_2, tindakan_makluman_3,
                   tindakan_makluman_4) VALUES (?,?,?,?,?,?,?,?)""",
                (minit_id, i + 1, mb.get('no_rujukan', ''), mb.get('perkara', ''),
                 mb.get('tindakan_makluman_1', ''), mb.get('tindakan_makluman_2', ''),
                 mb.get('tindakan_makluman_3', ''), mb.get('tindakan_makluman_4', ''))
            )

    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'simpan_minit',
              f"Minit ID: {minit_id}", get_client_ip())
    return jsonify({'success': True, 'message': 'Data berjaya disimpan.'})


@app.route('/minit/<int:minit_id>/padam', methods=['POST'])
@login_required
def minit_padam(minit_id):
    db = get_db()
    minit = db.execute("SELECT tajuk_mesyuarat, bil FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if minit:
        db.execute("DELETE FROM minit WHERE id = ? AND user_id = ?", (minit_id, session['user_id']))
        db.commit()
        log_audit(session['user_id'], session['email'], 'padam_minit',
                  f"Minit: {minit['tajuk_mesyuarat']} Bil. {minit['bil']}", get_client_ip())
    db.close()
    flash('Minit mesyuarat berjaya dipadam.', 'success')
    return redirect(url_for('dashboard'))


# ── Preview ──

@app.route('/minit/<int:minit_id>/pratonton')
@login_required
def minit_preview(minit_id):
    db = get_db()
    minit = db.execute("SELECT * FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if not minit:
        db.close()
        flash('Minit tidak dijumpai.', 'error')
        return redirect(url_for('dashboard'))

    kehadiran = db.execute(
        "SELECT * FROM kehadiran WHERE minit_id = ? ORDER BY kategori, urutan", (minit_id,)
    ).fetchall()

    seksyen_rows = db.execute(
        "SELECT * FROM seksyen WHERE minit_id = ? ORDER BY urutan", (minit_id,)
    ).fetchall()
    seksyen = []
    for s in seksyen_rows:
        perkara = db.execute(
            "SELECT * FROM perkara WHERE seksyen_id = ? ORDER BY urutan", (s['id'],)
        ).fetchall()
        seksyen.append({'seksyen': s, 'perkara': perkara})

    maklumbalas = db.execute(
        "SELECT * FROM maklumbalas WHERE minit_id = ? ORDER BY bil", (minit_id,)
    ).fetchall()

    db.close()

    kehadiran_dict = {
        'hadir': [k for k in kehadiran if k['kategori'] == 'hadir'],
        'tidak_hadir': [k for k in kehadiran if k['kategori'] == 'tidak_hadir'],
        'turut_hadir': [k for k in kehadiran if k['kategori'] == 'turut_hadir'],
        'urus_setia': [k for k in kehadiran if k['kategori'] == 'urus_setia'],
    }

    pencatat = next((k for k in kehadiran if k['is_pencatat']), None)
    pengerusi = next((k for k in kehadiran if k['is_pengerusi']), None)
    tarikh_formatted = format_tarikh_bm(minit['tarikh'])

    return render_template('preview.html',
                           minit=minit, kehadiran=kehadiran_dict,
                           seksyen=seksyen, maklumbalas=maklumbalas,
                           pencatat=pencatat, pengerusi=pengerusi,
                           tarikh_formatted=tarikh_formatted)


# ── Export ──

@app.route('/minit/<int:minit_id>/eksport/docx')
@login_required
def eksport_docx(minit_id):
    db = get_db()
    minit = db.execute("SELECT * FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if not minit:
        db.close()
        return "Minit tidak dijumpai", 404

    kehadiran = db.execute(
        "SELECT * FROM kehadiran WHERE minit_id = ? ORDER BY kategori, urutan", (minit_id,)
    ).fetchall()

    seksyen_rows = db.execute(
        "SELECT * FROM seksyen WHERE minit_id = ? ORDER BY urutan", (minit_id,)
    ).fetchall()
    seksyen = []
    for s in seksyen_rows:
        perkara = db.execute(
            "SELECT * FROM perkara WHERE seksyen_id = ? ORDER BY urutan", (s['id'],)
        ).fetchall()
        seksyen.append({'seksyen': s, 'perkara': perkara})

    maklumbalas = db.execute(
        "SELECT * FROM maklumbalas WHERE minit_id = ? ORDER BY bil", (minit_id,)
    ).fetchall()
    db.close()

    kehadiran_dict = {
        'hadir': [k for k in kehadiran if k['kategori'] == 'hadir'],
        'tidak_hadir': [k for k in kehadiran if k['kategori'] == 'tidak_hadir'],
        'turut_hadir': [k for k in kehadiran if k['kategori'] == 'turut_hadir'],
        'urus_setia': [k for k in kehadiran if k['kategori'] == 'urus_setia'],
    }

    pencatat = next((k for k in kehadiran if k['is_pencatat']), None)
    pengerusi = next((k for k in kehadiran if k['is_pengerusi']), None)
    tarikh_formatted = format_tarikh_bm(minit['tarikh'])

    doc_buffer = generate_docx(minit, kehadiran_dict, seksyen, maklumbalas,
                               pencatat, pengerusi, tarikh_formatted)

    filename = f"Minit_Mesyuarat_{minit['bil'].replace('/', '-')}_{minit['tajuk_mesyuarat'][:30]}.docx"

    user_dir = get_user_storage(session['user_id'])
    filepath = os.path.join(user_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(doc_buffer.getvalue())

    doc_buffer.seek(0)
    log_audit(session['user_id'], session['email'], 'eksport_docx',
              f"Minit ID: {minit_id} - {minit['tajuk_mesyuarat']} Bil. {minit['bil']}", get_client_ip())

    # HIPAA compliance: purge meeting content from database after export
    db = get_db()
    seksyen_ids = db.execute("SELECT id FROM seksyen WHERE minit_id = ?", (minit_id,)).fetchall()
    for s in seksyen_ids:
        db.execute("DELETE FROM perkara WHERE seksyen_id = ?", (s['id'],))
    db.execute("DELETE FROM seksyen WHERE minit_id = ?", (minit_id,))
    db.execute("DELETE FROM kehadiran WHERE minit_id = ?", (minit_id,))
    db.execute("DELETE FROM maklumbalas WHERE minit_id = ?", (minit_id,))
    db.execute("DELETE FROM minit WHERE id = ? AND user_id = ?", (minit_id, session['user_id']))
    db.commit()
    db.close()
    log_audit(session['user_id'], session['email'], 'padam_data_hipaa',
              f"Data minit ID {minit_id} dipadam selepas eksport (pematuhan HIPAA)", get_client_ip())

    return send_file(doc_buffer, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# ── Draft Save to User Storage ──

@app.route('/minit/<int:minit_id>/simpan-draf', methods=['POST'])
@login_required
def simpan_draf(minit_id):
    db = get_db()
    minit = db.execute("SELECT * FROM minit WHERE id = ? AND user_id = ?",
                       (minit_id, session['user_id'])).fetchone()
    if not minit:
        db.close()
        return jsonify({'error': 'Minit tidak dijumpai'}), 404

    db.execute("UPDATE minit SET status = 'draf', updated_at = datetime('now','localtime') WHERE id = ?",
               (minit_id,))
    db.commit()
    db.close()

    log_audit(session['user_id'], session['email'], 'simpan_draf',
              f"Minit ID: {minit_id}", get_client_ip())
    return jsonify({'success': True, 'message': 'Draf berjaya disimpan.'})


@app.route('/simpanan')
@login_required
def user_files():
    user_dir = get_user_storage(session['user_id'])
    files = []
    if os.path.exists(user_dir):
        for f in sorted(os.listdir(user_dir), reverse=True):
            filepath = os.path.join(user_dir, f)
            stat = os.stat(filepath)
            files.append({
                'name': f,
                'size': round(stat.st_size / 1024, 1),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M')
            })
    return render_template('simpanan.html', files=files)


@app.route('/simpanan/muat-turun/<path:filename>')
@login_required
def muat_turun_fail(filename):
    user_dir = get_user_storage(session['user_id'])
    filepath = os.path.join(user_dir, filename)
    if not os.path.exists(filepath):
        flash('Fail tidak dijumpai.', 'error')
        return redirect(url_for('user_files'))
    return send_file(filepath, as_attachment=True)


@app.route('/simpanan/padam/<path:filename>', methods=['POST'])
@login_required
def padam_fail(filename):
    user_dir = get_user_storage(session['user_id'])
    filepath = os.path.join(user_dir, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        flash('Fail berjaya dipadam.', 'success')
    return redirect(url_for('user_files'))


# ── Staff Management ──

@app.route('/kakitangan')
@login_required
def kakitangan_list():
    db = get_db()
    staff = db.execute("SELECT * FROM kakitangan ORDER BY jabatan, nama").fetchall()
    jabatan_list = db.execute("SELECT DISTINCT jabatan FROM kakitangan ORDER BY jabatan").fetchall()
    user_jabatan = ''
    peranan = session.get('peranan', 'pengguna')
    if peranan == 'admin':
        user = db.execute("SELECT jabatan FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()
        user_jabatan = user['jabatan'] or '' if user else ''
    db.close()
    can_edit = peranan in ('admin', 'superadmin')
    return render_template('staff.html', staff=staff, jabatan_list=jabatan_list,
                           is_admin=can_edit, is_superadmin=(peranan == 'superadmin'),
                           user_jabatan=user_jabatan)


@app.route('/kakitangan/tambah', methods=['POST'])
@admin_required
def kakitangan_tambah():
    data = request.get_json()
    if session.get('peranan') == 'admin':
        db = get_db()
        user = db.execute("SELECT jabatan FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()
        user_jabatan = user['jabatan'] or '' if user else ''
        if data.get('jabatan', '') != user_jabatan:
            db.close()
            return jsonify({'error': 'Anda hanya boleh menambah kakitangan dalam jabatan anda.'}), 403
        db.close()
    db = get_db()
    db.execute(
        "INSERT INTO kakitangan (nama, jawatan, jabatan, gelaran, gred) VALUES (?,?,?,?,?)",
        (data['nama'], data['jawatan'], data.get('jabatan', ''),
         data.get('gelaran', ''), data.get('gred', ''))
    )
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/kakitangan/<int:staff_id>/kemaskini', methods=['POST'])
@admin_required
def kakitangan_kemaskini(staff_id):
    data = request.get_json()
    db = get_db()
    if session.get('peranan') == 'admin':
        user = db.execute("SELECT jabatan FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()
        user_jabatan = user['jabatan'] or '' if user else ''
        staff = db.execute("SELECT jabatan FROM kakitangan WHERE id = ?", (staff_id,)).fetchone()
        if not staff or staff['jabatan'] != user_jabatan:
            db.close()
            return jsonify({'error': 'Anda hanya boleh mengemaskini kakitangan dalam jabatan anda.'}), 403
    db.execute(
        "UPDATE kakitangan SET nama=?, jawatan=?, jabatan=?, gelaran=?, gred=? WHERE id=?",
        (data['nama'], data['jawatan'], data.get('jabatan', ''),
         data.get('gelaran', ''), data.get('gred', ''), staff_id)
    )
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/kakitangan/<int:staff_id>/padam', methods=['POST'])
@admin_required
def kakitangan_padam(staff_id):
    db = get_db()
    if session.get('peranan') == 'admin':
        user = db.execute("SELECT jabatan FROM pengguna WHERE id = ?", (session['user_id'],)).fetchone()
        user_jabatan = user['jabatan'] or '' if user else ''
        staff = db.execute("SELECT jabatan FROM kakitangan WHERE id = ?", (staff_id,)).fetchone()
        if not staff or staff['jabatan'] != user_jabatan:
            db.close()
            return jsonify({'error': 'Anda hanya boleh menyahaktif kakitangan dalam jabatan anda.'}), 403
    db.execute("UPDATE kakitangan SET aktif = 0 WHERE id = ?", (staff_id,))
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/api/kakitangan/cari')
@login_required
def kakitangan_cari():
    q = request.args.get('q', '').strip()
    db = get_db()
    if q:
        staff = db.execute(
            "SELECT * FROM kakitangan WHERE aktif = 1 AND (nama LIKE ? OR jawatan LIKE ? OR jabatan LIKE ?) ORDER BY nama",
            (f'%{q}%', f'%{q}%', f'%{q}%')
        ).fetchall()
    else:
        staff = db.execute("SELECT * FROM kakitangan WHERE aktif = 1 ORDER BY jabatan, nama").fetchall()
    db.close()
    return jsonify([dict(s) for s in staff])


if __name__ == '__main__':
    app.run(debug=True, port=5000)
