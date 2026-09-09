// ── Tab Navigation ──
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    const tab = document.getElementById('tab-' + tabName);
    if (tab) tab.classList.add('active');
    event.target.classList.add('active');
    const label = document.getElementById('activeTabLabel');
    if (label) label.textContent = event.target.textContent;
    const wrapper = document.querySelector('.tab-nav-wrapper');
    if (wrapper) wrapper.classList.remove('open');
}

// ── Save Status ──
function showStatus(message, type) {
    const el = document.getElementById('saveStatus');
    if (!el) return;
    el.textContent = message;
    el.className = 'save-status ' + type;
    el.style.display = 'block';
    setTimeout(() => { el.style.display = 'none'; }, 3000);
}

// ── Collect Form Data ──
function collectData() {
    const data = {
        tajuk_mesyuarat: val('tajuk_mesyuarat'),
        bil: val('bil'),
        hospital: val('hospital'),
        tarikh: val('tarikh'),
        masa_mula: val('masa_mula'),
        masa_tamat: val('masa_tamat'),
        tempat: val('tempat'),
        kehadiran: collectKehadiran(),
        seksyen: collectSeksyen(),
        maklumbalas: collectMaklumBalas()
    };
    return data;
}

function val(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}

function collectKehadiran() {
    const result = {};
    ['hadir', 'tidak_hadir', 'turut_hadir', 'urus_setia'].forEach(kat => {
        const items = [];
        document.querySelectorAll(`#senarai-${kat} .attendance-item`).forEach(item => {
            items.push({
                kakitangan_id: item.querySelector('.att-kid')?.value || null,
                nama: item.querySelector('.att-nama')?.value || '',
                jawatan: item.querySelector('.att-jawatan')?.value || '',
                is_pengerusi: item.querySelector('.att-pengerusi')?.checked || false,
                is_pencatat: item.querySelector('.att-pencatat')?.checked || false,
                wakil_nama: item.querySelector('.att-wakil-nama')?.value || '',
                wakil_jawatan: item.querySelector('.att-wakil-jawatan')?.value || ''
            });
        });
        result[kat] = items;
    });
    return result;
}

function collectSeksyen() {
    const sections = [];
    document.querySelectorAll('#seksyen-container .section-card').forEach(card => {
        const perkara = [];
        card.querySelectorAll('.perkara-item').forEach((p, j) => {
            perkara.push({
                nombor: j + 1,
                kandungan: p.querySelector('.perkara-kandungan')?.value || '',
                tindakan: p.querySelector('.perkara-tindakan')?.value || '',
                pegawai: p.querySelector('.perkara-pegawai')?.value || '',
                status_tindakan: p.querySelector('.perkara-status')?.value || 'baru'
            });
        });
        sections.push({
            nombor_romawi: card.querySelector('.seksyen-romawi')?.value || '',
            tajuk: card.querySelector('.seksyen-tajuk')?.value || '',
            perkara: perkara
        });
    });
    return sections;
}

function collectMaklumBalas() {
    const rows = [];
    document.querySelectorAll('#tblMaklumBalas tbody tr').forEach(row => {
        rows.push({
            no_rujukan: row.querySelector('.mb-rujukan')?.value || '',
            perkara: row.querySelector('.mb-perkara')?.value || '',
            tindakan_makluman_1: row.querySelector('.mb-tindakan1')?.value || '',
            tindakan_makluman_2: row.querySelector('.mb-tindakan2')?.value || ''
        });
    });
    return rows;
}

// ── Save ──
async function simpanMinit() {
    const btn = document.getElementById('btnSimpan');
    if (btn) { btn.disabled = true; btn.textContent = 'Menyimpan...'; }
    try {
        const data = collectData();
        const resp = await fetch(`/minit/${MINIT_ID}/simpan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await resp.json();
        if (result.success) {
            showStatus('Data berjaya disimpan!', 'success');
        } else {
            showStatus('Ralat: ' + (result.error || 'Gagal menyimpan'), 'error');
        }
    } catch (e) {
        showStatus('Ralat rangkaian. Sila cuba lagi.', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Simpan'; }
    }
}

// ── Staff Search ──
let searchTimeout;
async function cariStaff(query) {
    clearTimeout(searchTimeout);
    const container = document.getElementById('hasilCarian');
    if (!query || query.length < 2) {
        container.style.display = 'none';
        return;
    }
    searchTimeout = setTimeout(async () => {
        try {
            const resp = await fetch(`/api/kakitangan/cari?q=${encodeURIComponent(query)}`);
            const staff = await resp.json();
            if (staff.length === 0) {
                container.innerHTML = '<div style="padding:12px;color:#999;text-align:center">Tiada kakitangan dijumpai</div>';
            } else {
                container.innerHTML = staff.map(s => `
                    <div class="search-result-item">
                        <div class="staff-info">
                            <div class="staff-name">${escHtml(s.nama)}</div>
                            <div class="staff-detail">${escHtml(s.jawatan)} | ${escHtml(s.jabatan || '-')}</div>
                        </div>
                        <div class="add-buttons">
                            <button class="btn btn-sm btn-primary" onclick="tambahDariCarian(${s.id},'${escAttr(s.nama)}','${escAttr(s.jawatan)}','hadir')">Hadir</button>
                            <button class="btn btn-sm btn-warning" onclick="tambahDariCarian(${s.id},'${escAttr(s.nama)}','${escAttr(s.jawatan)}','tidak_hadir')">Tidak Hadir</button>
                            <button class="btn btn-sm btn-info" onclick="tambahDariCarian(${s.id},'${escAttr(s.nama)}','${escAttr(s.jawatan)}','turut_hadir')">Turut Hadir</button>
                            <button class="btn btn-sm btn-secondary" onclick="tambahDariCarian(${s.id},'${escAttr(s.nama)}','${escAttr(s.jawatan)}','urus_setia')">Urus Setia</button>
                        </div>
                    </div>
                `).join('');
            }
            container.style.display = 'block';
        } catch (e) {
            container.innerHTML = '<div style="padding:12px;color:red">Ralat carian</div>';
            container.style.display = 'block';
        }
    }, 300);
}

function tambahDariCarian(id, nama, jawatan, kategori) {
    tambahKehadiran(kategori, id, nama, jawatan);
    document.getElementById('cariKakitangan').value = '';
    document.getElementById('hasilCarian').style.display = 'none';
}

// ── Attendance Management ──
function tambahKehadiran(kategori, kakitanganId, nama, jawatan) {
    const list = document.getElementById('senarai-' + kategori);
    if (!list) return;
    const count = list.querySelectorAll('.attendance-item').length + 1;

    const isHadir = kategori === 'hadir';
    const isUrusSetia = kategori === 'urus_setia';

    const div = document.createElement('div');
    div.className = 'attendance-item';
    div.dataset.kategori = kategori;
    div.innerHTML = `
        <div class="attendance-info">
            <span class="attendance-num">${count}.</span>
            <div class="attendance-detail">
                <input type="text" class="inline-input att-jawatan" value="${escAttr(jawatan)}" placeholder="Jawatan">
                <input type="text" class="inline-input att-nama" value="${escAttr(nama)}" placeholder="Nama">
                <input type="hidden" class="att-kid" value="${kakitanganId || ''}">
            </div>
        </div>
        <div class="attendance-options">
            ${isHadir ? `
            <label class="checkbox-label"><input type="checkbox" class="att-pengerusi"> Pengerusi</label>
            <label class="checkbox-label"><input type="checkbox" class="att-pencatat"> Pencatat</label>
            <div class="wakil-section">
                <label class="small-label">Diwakili oleh:</label>
                <input type="text" class="inline-input att-wakil-nama" placeholder="Nama wakil">
                <input type="text" class="inline-input att-wakil-jawatan" placeholder="Jawatan wakil">
            </div>
            ` : ''}
            ${isUrusSetia ? `
            <label class="checkbox-label"><input type="checkbox" class="att-pencatat"> Pencatat Minit</label>
            ` : ''}
            <button class="btn btn-sm btn-danger" onclick="buangKehadiran(this)">Buang</button>
        </div>
    `;
    list.appendChild(div);
    renumberAttendance(kategori);
}

function tambahKehadiranManual(kategori) {
    tambahKehadiran(kategori, '', '', '');
    const list = document.getElementById('senarai-' + kategori);
    const last = list.querySelector('.attendance-item:last-child .att-jawatan');
    if (last) last.focus();
}

function buangKehadiran(btn) {
    const item = btn.closest('.attendance-item');
    const kategori = item.dataset.kategori;
    item.remove();
    renumberAttendance(kategori);
}

function renumberAttendance(kategori) {
    const list = document.getElementById('senarai-' + kategori);
    if (!list) return;
    list.querySelectorAll('.attendance-item').forEach((item, i) => {
        const num = item.querySelector('.attendance-num');
        if (num) num.textContent = (i + 1) + '.';
    });
}

// ── Section Management ──
function tambahSeksyen() {
    const container = document.getElementById('seksyen-container');
    const count = container.querySelectorAll('.section-card').length;
    const romawi = (typeof ROMAWI !== 'undefined' && ROMAWI[count]) ? ROMAWI[count] : (count + 1).toString();

    const div = document.createElement('div');
    div.className = 'card section-card';
    div.innerHTML = `
        <div class="section-header">
            <div class="section-title-row">
                <input type="text" class="inline-input seksyen-romawi" value="${romawi}"
                       placeholder="I" style="width:60px;text-align:center;font-weight:bold">
                <span class="section-dot">.</span>
                <input type="text" class="inline-input seksyen-tajuk" value=""
                       placeholder="Tajuk Seksyen" style="font-weight:bold;text-transform:uppercase">
            </div>
            <div class="section-actions">
                <button class="btn btn-sm btn-primary" onclick="tambahPerkara(this)">+ Perkara</button>
                <button class="btn btn-sm btn-danger" onclick="buangSeksyen(this)">Buang Seksyen</button>
            </div>
        </div>
        <div class="perkara-container"></div>
    `;
    container.appendChild(div);
    div.querySelector('.seksyen-tajuk').focus();
}

function buangSeksyen(btn) {
    if (confirm('Padam seksyen ini dan semua perkara di dalamnya?')) {
        btn.closest('.section-card').remove();
    }
}

function tambahPerkara(btn) {
    const card = btn.closest('.section-card');
    const container = card.querySelector('.perkara-container');
    const count = container.querySelectorAll('.perkara-item').length + 1;

    const div = document.createElement('div');
    div.className = 'perkara-item';
    div.innerHTML = `
        <div class="perkara-header">
            <span class="perkara-num">${count}.</span>
            <button class="btn btn-xs btn-danger" onclick="buangPerkara(this)">x</button>
        </div>
        <div class="perkara-body">
            <textarea class="perkara-kandungan" placeholder="Kandungan perbincangan..." rows="3"></textarea>
            <div class="perkara-action-row">
                <div class="form-group">
                    <label class="small-label">Tindakan</label>
                    <select class="perkara-tindakan">
                        <option value="">-- Pilih Tindakan --</option>
                        <option value="makluman">Untuk Makluman</option>
                        <option value="tindakan">Untuk Tindakan</option>
                        <option value="keputusan">Keputusan</option>
                        <option value="perbincangan">Untuk Perbincangan</option>
                        <option value="cadangan">Cadangan</option>
                        <option value="ulasan">Ulasan</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="small-label">Pegawai Bertanggungjawab</label>
                    <input type="text" class="perkara-pegawai" placeholder="Nama pegawai">
                </div>
                <div class="form-group">
                    <label class="small-label">Status</label>
                    <select class="perkara-status">
                        <option value="baru">Baru</option>
                        <option value="dalam_tindakan">Dalam Tindakan</option>
                        <option value="selesai">Selesai</option>
                    </select>
                </div>
            </div>
        </div>
    `;
    container.appendChild(div);
    div.querySelector('.perkara-kandungan').focus();
}

function buangPerkara(btn) {
    const item = btn.closest('.perkara-item');
    const container = item.parentElement;
    item.remove();
    container.querySelectorAll('.perkara-item').forEach((p, i) => {
        const num = p.querySelector('.perkara-num');
        if (num) num.textContent = (i + 1) + '.';
    });
}

// ── Maklum Balas ──
function tambahMaklumBalas() {
    const tbody = document.querySelector('#tblMaklumBalas tbody');
    const count = tbody.querySelectorAll('tr').length + 1;
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="table-input mb-bil" value="${count}" style="width:40px"></td>
        <td><input type="text" class="table-input mb-rujukan"></td>
        <td><textarea class="table-input mb-perkara" rows="2"></textarea></td>
        <td><textarea class="table-input mb-tindakan1" rows="2"></textarea></td>
        <td><textarea class="table-input mb-tindakan2" rows="2"></textarea></td>
        <td><button class="btn btn-xs btn-danger" onclick="buangMaklumBalas(this)">x</button></td>
    `;
    tbody.appendChild(tr);
}

function buangMaklumBalas(btn) {
    btn.closest('tr').remove();
    document.querySelectorAll('#tblMaklumBalas tbody tr').forEach((row, i) => {
        const bil = row.querySelector('.mb-bil');
        if (bil) bil.value = i + 1;
    });
}

// ── Utility ──
function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ── Keyboard shortcut Ctrl+S to save ──
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (typeof simpanMinit === 'function' && document.getElementById('btnSimpan')) {
            simpanMinit();
        }
    }
});
