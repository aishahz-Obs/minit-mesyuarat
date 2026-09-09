import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get('DATABASE_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'minit_mesyuarat.db'))

os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)

ADMIN_EMAIL = 'aishahz@moh.gov.my'
DEFAULT_PASSWORD = 'HSA@2026'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS pengguna (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nama TEXT NOT NULL,
            jawatan TEXT,
            jabatan TEXT,
            peranan TEXT DEFAULT 'pengguna',
            status TEXT DEFAULT 'menunggu',
            approved_by INTEGER,
            approved_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS audit_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_email TEXT,
            tindakan TEXT NOT NULL,
            butiran TEXT,
            ip_address TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS kakitangan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            jawatan TEXT NOT NULL,
            jabatan TEXT,
            gelaran TEXT,
            gred TEXT,
            aktif INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS minit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tajuk_mesyuarat TEXT NOT NULL,
            bil TEXT NOT NULL,
            hospital TEXT DEFAULT 'HOSPITAL SHAH ALAM',
            tarikh TEXT,
            hari TEXT,
            masa_mula TEXT,
            masa_tamat TEXT,
            tempat TEXT DEFAULT 'Bilik Persidangan, Aras 2',
            status TEXT DEFAULT 'draf',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES pengguna(id)
        );

        CREATE TABLE IF NOT EXISTS kehadiran (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            minit_id INTEGER NOT NULL,
            kakitangan_id INTEGER,
            nama TEXT,
            jawatan TEXT,
            kategori TEXT NOT NULL,
            is_pengerusi INTEGER DEFAULT 0,
            is_pencatat INTEGER DEFAULT 0,
            wakil_nama TEXT,
            wakil_jawatan TEXT,
            urutan INTEGER DEFAULT 0,
            FOREIGN KEY (minit_id) REFERENCES minit(id) ON DELETE CASCADE,
            FOREIGN KEY (kakitangan_id) REFERENCES kakitangan(id)
        );

        CREATE TABLE IF NOT EXISTS seksyen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            minit_id INTEGER NOT NULL,
            nombor_romawi TEXT NOT NULL,
            tajuk TEXT NOT NULL,
            urutan INTEGER DEFAULT 0,
            FOREIGN KEY (minit_id) REFERENCES minit(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS perkara (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seksyen_id INTEGER NOT NULL,
            nombor INTEGER,
            kandungan TEXT,
            tindakan TEXT,
            pegawai TEXT,
            status_tindakan TEXT DEFAULT 'baru',
            urutan INTEGER DEFAULT 0,
            FOREIGN KEY (seksyen_id) REFERENCES seksyen(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS maklumbalas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            minit_id INTEGER NOT NULL,
            bil INTEGER,
            no_rujukan TEXT,
            perkara TEXT,
            tindakan_makluman_1 TEXT,
            tindakan_makluman_2 TEXT,
            tindakan_makluman_3 TEXT,
            tindakan_makluman_4 TEXT,
            FOREIGN KEY (minit_id) REFERENCES minit(id) ON DELETE CASCADE
        );
    ''')

    # Migrate: add columns if missing (for existing databases)
    try:
        c.execute("SELECT peranan FROM pengguna LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE pengguna ADD COLUMN peranan TEXT DEFAULT 'pengguna'")
        c.execute("ALTER TABLE pengguna ADD COLUMN status TEXT DEFAULT 'aktif'")
        c.execute("ALTER TABLE pengguna ADD COLUMN approved_by INTEGER")
        c.execute("ALTER TABLE pengguna ADD COLUMN approved_at TEXT")

    try:
        c.execute("SELECT email FROM pengguna LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE pengguna ADD COLUMN email TEXT")
        c.execute("UPDATE pengguna SET email = username WHERE email IS NULL")

    # Seed admin if not exists
    admin = c.execute("SELECT id FROM pengguna WHERE email = ?", (ADMIN_EMAIL,)).fetchone()
    if not admin:
        c.execute(
            """INSERT INTO pengguna (email, password_hash, nama, jawatan, jabatan, peranan, status)
               VALUES (?,?,?,?,?,?,?)""",
            (ADMIN_EMAIL, generate_password_hash(DEFAULT_PASSWORD),
             'Aisha binti Zakaria', 'Pegawai Tadbir', 'Pentadbiran', 'admin', 'aktif')
        )

    # Seed staff if empty
    count = c.execute("SELECT COUNT(*) FROM kakitangan").fetchone()[0]
    if count == 0:
        staff = [
            ("Dr. Ruzita binti Othman", "Pengarah Hospital", "Pentadbiran", "Dr.", "JUSA C"),
            ("Dr. Ahmad bin Hassan", "Timbalan Pengarah (Perubatan)", "Pentadbiran", "Dr.", "UD56"),
            ("Pn. Siti Aminah binti Yusof", "Timbalan Pengarah (Pengurusan)", "Pentadbiran", "Pn.", "N48"),
            ("Dr. Mohd Rizal bin Abdullah", "Ketua Jabatan Ortopedik", "Ortopedik", "Dr.", "UD54"),
            ("Dr. Faizah binti Karim", "Ketua Jabatan Obstetrik & Ginekologi", "O&G", "Dr.", "UD54"),
            ("Dr. Tan Wei Ming", "Ketua Jabatan Pediatrik", "Pediatrik", "Dr.", "UD54"),
            ("Dr. Nurul Huda binti Ismail", "Ketua Jabatan Perubatan", "Perubatan", "Dr.", "UD54"),
            ("Dr. Lee Chong Wei", "Ketua Jabatan Pembedahan", "Pembedahan", "Dr.", "UD54"),
            ("Dr. Rashid bin Omar", "Ketua Jabatan Anestesiologi", "Anestesiologi", "Dr.", "UD54"),
            ("Dr. Aishah binti Mahmud", "Ketua Jabatan Radiologi", "Radiologi", "Dr.", "UD54"),
            ("Dr. Kumar a/l Subramaniam", "Ketua Jabatan Patologi", "Patologi", "Dr.", "UD54"),
            ("Dr. Norazlina binti Samad", "Ketua Jabatan Psikiatri", "Psikiatri", "Dr.", "UD54"),
            ("Dr. Hafiz bin Zakaria", "Ketua Jabatan Kecemasan", "Kecemasan", "Dr.", "UD54"),
            ("Dr. Zainab binti Ali", "Pakar Perubatan Keluarga", "Perubatan Keluarga", "Dr.", "UD52"),
            ("Dr. Lim Siew Fong", "Pakar Perubatan", "Perubatan", "Dr.", "UD52"),
            ("Dr. Nadia binti Rosli", "Pakar Pediatrik", "Pediatrik", "Dr.", "UD52"),
            ("Dr. Wan Azmi bin Wan Ismail", "Pakar Pembedahan", "Pembedahan", "Dr.", "UD52"),
            ("Dr. Farah binti Zainal", "Pakar O&G", "O&G", "Dr.", "UD52"),
            ("Pn. Rohana binti Mohamad", "Ketua Jururawat", "Kejururawatan", "Pn.", "U36"),
            ("En. Razak bin Harun", "Pegawai Farmasi", "Farmasi", "En.", "UF44"),
            ("Pn. Mariam binti Salleh", "Pegawai Dietetik", "Dietetik", "Pn.", "U32"),
            ("En. Azlan bin Kadir", "Pegawai Sains (Makmal)", "Patologi", "En.", "C44"),
            ("Pn. Norhaliza binti Jaafar", "Pegawai Tadbir", "Pentadbiran", "Pn.", "N32"),
            ("En. Hafizi bin Razali", "Pegawai Teknologi Maklumat", "IT", "En.", "F32"),
            ("Pn. Syafiqah binti Idris", "Pegawai Kualiti", "Kualiti", "Pn.", "N32"),
            ("En. Khairul Anwar bin Roslan", "Pegawai Rekod Perubatan", "Rekod Perubatan", "En.", "N28"),
            ("Pn. Haslinda binti Ahmad", "Penolong Pegawai Tadbir", "Pentadbiran", "Pn.", "N28"),
            ("En. Faizul bin Daud", "Jururawat Masyarakat", "Kejururawatan", "En.", "U29"),
            ("Pn. Zalina binti Ghazali", "Pegawai Kerja Sosial Perubatan", "Kerja Sosial", "Pn.", "S32"),
            ("En. Haziq bin Noor", "Juruteknik Perubatan", "Kejuruteraan Biomedikal", "En.", "J29"),
        ]
        c.executemany(
            "INSERT INTO kakitangan (nama, jawatan, jabatan, gelaran, gred) VALUES (?,?,?,?,?)",
            staff
        )

    conn.commit()
    conn.close()


def log_audit(user_id, user_email, tindakan, butiran='', ip=''):
    conn = get_db()
    conn.execute(
        "INSERT INTO audit_trail (user_id, user_email, tindakan, butiran, ip_address) VALUES (?,?,?,?,?)",
        (user_id, user_email, tindakan, butiran, ip)
    )
    conn.commit()
    conn.close()


def seed_default_sections(minit_id):
    conn = get_db()
    c = conn.cursor()
    sections = [
        ("I", "PERUTUSAN PENGERUSI", 1),
        ("II", "PENGESAHAN MINIT MESYUARAT", 2),
        ("III", "HAL-HAL BERBANGKIT", 3),
        ("IV", "PERKARA YANG DIBINCANGKAN", 4),
        ("V", "HAL-HAL LAIN", 5),
        ("VI", "PENUTUP", 6),
    ]
    for romawi, tajuk, urutan in sections:
        c.execute(
            "INSERT INTO seksyen (minit_id, nombor_romawi, tajuk, urutan) VALUES (?,?,?,?)",
            (minit_id, romawi, tajuk, urutan)
        )
    conn.commit()
    conn.close()
