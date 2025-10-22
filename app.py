# v1.5.1
# - Fix: AGGRID_ENABLED name (typo earlier as AGRID_ENABLED) to prevent NameError in show_table
# - Preserve v1.5.0 bilingual UI (EN/ES), locked Perform Count fields (only Counted QTY + Note editable),
#   Submit Assignment flow, safe submit handler, sound/vibration ON, 20-min lock, and default mapping

import os, time, uuid, re, json
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ---------------- I18N ----------------
I18N = {
    "en": {
        "tab_assign": "Assign Counts",
        "tab_my": "My Assignments",
        "tab_perform": "Perform Count",
        "tab_dash": "Dashboard (Live)",
        "tab_disc": "Discrepancies",
        "tab_settings": "Settings",
        "app_name": "Cycle Counting",
        "active_dir": "Active log dir",
        "tz": "Timezone",
        "lock": "Lock",
        "minutes": "min",
        "lang": "Language / Idioma",
        "lang_en": "English (EN)",
        "lang_es": "Español (ES)",
        "assign_title": "Assign Counts",
        "assigned_by": "Assigned by",
        "assign_to": "Assign to (name)",
        "hint_assign": "Select multiple locations and/or paste a list. Other fields auto‑fill from the inventory cache.",
        "locations": "Locations",
        "paste_locs": "Paste locations (optional)",
        "notes": "Notes (optional)",
        "create_assign": "Create Assignments",
        "all_assign": "All Assignments",
        "no_assign": "No assignments yet.",
        "created_n": "Created {n} assignment(s) for {name}.",
        "dup_skipped": "Skipped {n} duplicate location(s) already Assigned/In Progress: {sample}",
        "locked_skipped": "Skipped {n} location(s) currently locked by another user.",
        "not_in_cache": "{n} location(s) not in inventory cache (FYI): {sample}",
        "available": "Available",
        "locked_by_until": "🔒 {who} until {until}",
        "my_title": "My Assignments",
        "i_am": "I am (name)",
        "open": "Open",
        "in_progress": "In Progress",
        "submitted": "Submitted",
        "total": "Total",
        "your_assign": "Your Assignments",
        "radio_label": "Select an assignment",
        "selected_summary": "**Selected:** `{id}` — **Location:** `{loc}` — **Status:** `{status}`",
        "submit_assignment": "Submit Assignment (Open Perform Count)",
        "err_enter_name": "Enter your name above to continue.",
        "err_missing": "Assignment no longer exists.",
        "err_belongs_to": "This assignment belongs to {assignee}.",
        "err_already_submitted": "This assignment is already Submitted.",
        "err_locked_other": "Locked by {who} until {until}",
        "lock_success_opening": "{msg} — Opening Perform Count…",
        "tip_submit_once": "Tip: Click an assignment, then press 'Submit Assignment' to open Perform Count.",
        "perform_title": "Perform Count",
        "auto_focus_loc": "Auto-focus Location",
        "auto_advance": "Auto-advance after scan",
        "assignment_id": "Assignment ID",
        "assignee": "Assignee",
        "scan_location": "Scan Location",
        "scan_pallet": "Scan Pallet ID (optional)",
        "sku": "SKU (optional)",
        "lot": "LOT Number (optional)",
        "expected_qty": "Expected QTY (from Assignment/Inventory)",
        "counted_qty": "Counted QTY",
        "note": "Note (optional)",
        "submit_count": "Submit Count",
        "warn_need_fields": "Assignee and Location are required.",
        "warn_count_invalid": "Enter a valid non-negative integer for Counted QTY.",
        "submitted_ok": "Submitted",
        "dash_title": "Dashboard (Live)",
        "auto_refresh_sec": "Auto-refresh every (seconds)",
        "subs_file": "Submissions file",
        "counts_today": "Counts Today",
        "over": "Over",
        "short": "Short",
        "match": "Match",
        "latest_subs": "Latest Submissions",
        "disc_title": "Discrepancies",
        "exceptions": "Exceptions",
        "export_ex": "Export Exceptions CSV",
        "settings_title": "Settings",
        "env_vars": "Environment variables (optional):",
        "tip_dir": "Tip: point CYCLE_COUNT_LOG_DIR to your OneDrive JT Logistics folder so counters and your dashboard use the same files.",
        "active_paths": "Active paths:",
        "inv_upload_title": "Inventory Excel — Upload & Map",
        "inv_cache_loaded": "Inventory cache loaded: {n} rows",
        "preview_first10": "Preview (first 10 rows):",
        "column_mapping": "Column Mapping",
        "map_loc": "Location",
        "map_sku": "SKU",
        "map_lot": "LOT Number",
        "map_pal": "Pallet ID",
        "map_qty": "Expected QTY",
        "save_map": "Save Mapping & Cache Inventory",
        "excel_err": "Excel load/mapping error: {err}",
        "no_data": "No data",
    },
    "es": {
        "tab_assign": "Asignar Conteos",
        "tab_my": "Mis Asignaciones",
        "tab_perform": "Realizar Conteo",
        "tab_dash": "Tablero (En Vivo)",
        "tab_disc": "Discrepancias",
        "tab_settings": "Configuración",
        "app_name": "Conteo Cíclico",
        "active_dir": "Carpeta de registros",
        "tz": "Zona horaria",
        "lock": "Bloqueo",
        "minutes": "min",
        "lang": "Idioma / Language",
        "lang_en": "English (EN)",
        "lang_es": "Español (ES)",
        "assign_title": "Asignar Conteos",
        "assigned_by": "Asignado por",
        "assign_to": "Asignar a (nombre)",
        "hint_assign": "Seleccione varias ubicaciones y/o pegue una lista. Los demás campos se completan desde el inventario.",
        "locations": "Ubicaciones",
        "paste_locs": "Pegar ubicaciones (opcional)",
        "notes": "Notas (opcional)",
        "create_assign": "Crear Asignaciones",
        "all_assign": "Todas las Asignaciones",
        "no_assign": "Aún no hay asignaciones.",
        "created_n": "Se crearon {n} asignación(es) para {name}.",
        "dup_skipped": "Omitidas {n} ubicaciones duplicadas ya Asignadas/En Progreso: {sample}",
        "locked_skipped": "Omitidas {n} ubicaciones actualmente bloqueadas por otro usuario.",
        "not_in_cache": "{n} ubicación(es) no están en el inventario (FYI): {sample}",
        "available": "Disponible",
        "locked_by_until": "🔒 {who} hasta {until}",
        "my_title": "Mis Asignaciones",
        "i_am": "Yo soy (nombre)",
        "open": "Abiertas",
        "in_progress": "En Progreso",
        "submitted": "Enviadas",
        "total": "Total",
        "your_assign": "Tus Asignaciones",
        "radio_label": "Selecciona una asignación",
        "selected_summary": "**Seleccionada:** `{id}` — **Ubicación:** `{loc}` — **Estado:** `{status}`",
        "submit_assignment": "Enviar Asignación (Abrir Realizar Conteo)",
        "err_enter_name": "Ingresa tu nombre arriba para continuar.",
        "err_missing": "La asignación ya no existe.",
        "err_belongs_to": "Esta asignación pertenece a {assignee}.",
        "err_already_submitted": "Esta asignación ya fue Enviada.",
        "err_locked_other": "Bloqueada por {who} hasta {until}",
        "lock_success_opening": "{msg} — Abriendo Realizar Conteo…",
        "tip_submit_once": "Tip: Haz clic en una asignación y luego en 'Enviar Asignación' para abrir Realizar Conteo.",
        "perform_title": "Realizar Conteo",
        "auto_focus_loc": "Autoenfocar Ubicación",
        "auto_advance": "Avanzar automáticamente después del escaneo",
        "assignment_id": "ID de Asignación",
        "assignee": "Asignado a",
        "scan_location": "Escanear Ubicación",
        "scan_pallet": "Escanear ID de Tarima (opcional)",
        "sku": "SKU (opcional)",
        "lot": "Número de Lote (opcional)",
        "expected_qty": "Cantidad Esperada (de Asignación/Inventario)",
        "counted_qty": "Cantidad Contada",
        "note": "Nota (opcional)",
        "submit_count": "Enviar Conteo",
        "warn_need_fields": "Se requieren Asignado a y Ubicación.",
        "warn_count_invalid": "Ingresa un entero válido (no negativo) para Cantidad Contada.",
        "submitted_ok": "Enviado",
        "dash_title": "Tablero (En Vivo)",
        "auto_refresh_sec": "Auto-actualizar cada (segundos)",
        "subs_file": "Archivo de Envíos",
        "counts_today": "Conteos Hoy",
        "over": "Sobrante",
        "short": "Faltante",
        "match": "Igual",
        "latest_subs": "Envíos Recientes",
        "disc_title": "Discrepancias",
        "exceptions": "Excepciones",
        "export_ex": "Exportar CSV de Excepciones",
        "settings_title": "Configuración",
        "env_vars": "Variables de entorno (opcional):",
        "tip_dir": "Tip: apunta CYCLE_COUNT_LOG_DIR a tu carpeta de OneDrive JT Logistics para compartir archivos.",
        "active_paths": "Rutas activas:",
        "inv_upload_title": "Inventario Excel — Cargar y Mapear",
        "inv_cache_loaded": "Inventario cargado: {n} filas",
        "preview_first10": "Vista previa (primeras 10 filas):",
        "column_mapping": "Mapeo de Columnas",
        "map_loc": "Ubicación",
        "map_sku": "SKU",
        "map_lot": "Número de Lote",
        "map_pal": "ID de Tarima",
        "map_qty": "Cantidad Esperada",
        "save_map": "Guardar Mapeo y Cachear Inventario",
        "excel_err": "Error al cargar/mapear Excel: {err}",
        "no_data": "Sin datos",
    },
}

def _lang_default():
    env = (os.getenv("CC_LANG","") or "").strip().lower()
    return "es" if env == "es" else "en"

def _ensure_default(k, v):
    if k not in st.session_state: st.session_state[k] = v

def t(key: str, **fmt):
    lang = st.session_state.get("lang", _lang_default())
    s = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
    if fmt:
        try: return s.format(**fmt)
        except Exception: return s
    return s

# --- AgGrid import
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    _AGGRID_IMPORTED = True
except Exception:
    _AGGRID_IMPORTED = False

APP_NAME = "Cycle Counting"
VERSION = "v1.5.1 (EN/ES + AGGRID fix)"
TZ_LABEL = "US/Central"
LOCK_MINUTES_DEFAULT = 20
LOCK_MINUTES = int(os.getenv("CC_LOCK_MINUTES", LOCK_MINUTES_DEFAULT))
TS_FMT = "%m/%d/%Y %I:%M:%S %p"

DEFAULT_MAPPING = {
    "location": "LocationName",
    "sku": "WarehouseSku",
    "lot_number": "CustomerLotReference",
    "pallet_id": "PalletId",
    "expected_qty": "QtyAvailable",
}

def lot_normalize(x: str) -> str:
    if x is None or (isinstance(x,float) and pd.isna(x)): return ""
    s = re.sub(r"\D", "", str(x)); s = re.sub(r"^0+", "", s)
    return s or ""

def ensure_dirs(paths):
    for p in paths: os.makedirs(p, exist_ok=True)

def get_paths():
    base = os.getenv("CYCLE_COUNT_LOG_DIR") or os.getenv("BIN_HELPER_LOG_DIR") or os.path.join(os.getcwd(), "logs")
    cloud = "/mount/src/bin-helper/logs"
    active = cloud if os.path.isdir(cloud) else base
    ensure_dirs([active])
    return {
        "root": active,
        "assign": os.path.join(active, "counts_assignments.csv"),
        "assign_deleted": os.path.join(active, "counts_assignments_deleted.csv"),
        "subs": os.path.join(active, "cyclecount_submissions.csv"),
        "inv_csv": os.path.join(active, "inventory_lookup.csv"),
        "inv_map": os.path.join(active, "inventory_mapping.json"),
    }

PATHS = get_paths()

ASSIGN_COLS = [
    "assignment_id","assigned_by","assignee","location","sku","lot_number","pallet_id",
    "expected_qty","priority","status","created_ts","due_date","notes",
    "lock_owner","lock_start_ts","lock_expires_ts"
]
SUBMIT_COLS = [
    "submission_id","assignment_id","assignee","location","sku","lot_number","pallet_id",
    "counted_qty","expected_qty","variance","variance_flag","timestamp","device_id","note"
]

_ENCODINGS = ["utf-8", "cp1252", "latin-1"]

def read_csv_fallback(fp, dtype=str):
    last_err = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(fp, dtype=dtype, encoding=enc).fillna("")
        except Exception as e:
            last_err = e; continue
    try:
        return pd.read_csv(fp, dtype=dtype, encoding="latin-1", on_bad_lines="skip").fillna("")
    except Exception as e2:
        raise last_err or e2

def dataframe_to_csv_utf8(df: pd.DataFrame, out_path: str):
    df.to_csv(out_path, index=False, encoding="utf-8")

def safe_append_csv(path, row: dict, columns: list):
    exists = os.path.exists(path)
    df = pd.DataFrame([row], columns=columns)
    tmp = path + ".tmp"
    if exists:
        with open(tmp, "a", encoding="utf-8") as f: df.to_csv(f, header=False, index=False)
        with open(tmp, "rb") as fin, open(path, "ab") as fout: fout.write(fin.read())
        os.remove(tmp)
    else:
        df.to_csv(path, index=False, encoding="utf-8")

def read_csv_locked(path, columns=None):
    if not os.path.exists(path): return pd.DataFrame(columns=columns or [])
    for _ in range(5):
        try: return read_csv_fallback(path, dtype=str)
        except Exception: time.sleep(0.1)
    return pd.DataFrame(columns=columns or [])

def now_str(): return datetime.now().strftime(TS_FMT)
def mk_id(prefix): return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
def parse_ts(s: str):
    try: return datetime.strptime(s, TS_FMT)
    except Exception: return None

def load_assignments():
    df = read_csv_locked(PATHS["assign"], ASSIGN_COLS)
    for c in ["lock_owner","lock_start_ts","lock_expires_ts"]:
        if c not in df.columns: df[c] = ""
    return df

def save_assignments(df: pd.DataFrame):
    for c in ASSIGN_COLS:
        if c not in df.columns: df[c] = ""
    dataframe_to_csv_utf8(df[ASSIGN_COLS], PATHS["assign"])

def load_submissions(): return read_csv_locked(PATHS["subs"], SUBMIT_COLS)

def load_cached_inventory() -> pd.DataFrame:
    if "inv_df" in st.session_state: return st.session_state["inv_df"]
    if os.path.exists(PATHS["inv_csv"]):
        try:
            inv = read_csv_fallback(PATHS["inv_csv"], dtype=str).fillna("")
            st.session_state["inv_df"] = inv; return inv
        except Exception: pass
    return pd.DataFrame(columns=["location","sku","lot_number","pallet_id","expected_qty"])

def save_inventory_cache(df: pd.DataFrame):
    dataframe_to_csv_utf8(df, PATHS["inv_csv"])
    st.session_state["inv_df"] = df

def save_inventory_mapping(mapping: dict):
    with open(PATHS["inv_map"], "w", encoding="utf-8") as f: json.dump(mapping, f, indent=2)

def load_inventory_mapping() -> dict:
    if os.path.exists(PATHS["inv_map"]):
        try: return json.load(open(PATHS["inv_map"], "r", encoding="utf-8"))
        except Exception: return {}
    return {}

def normalize_inventory_df(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = pd.DataFrame()
    out["location"]   = df[mapping.get("location","")].astype(str) if mapping.get("location","")   in df.columns else ""
    out["sku"]        = df[mapping.get("sku","")].astype(str)       if mapping.get("sku","")        in df.columns else ""
    lot_col = mapping.get("lot_number","")
    out["lot_number"] = df[lot_col].astype(str).map(lot_normalize)  if lot_col in df.columns else ""
    out["pallet_id"]  = df[mapping.get("pallet_id","")].astype(str) if mapping.get("pallet_id","")  in df.columns else ""
    qty_col = mapping.get("expected_qty","")
    if qty_col in df.columns:
        q = pd.to_numeric(df[qty_col], errors="coerce").fillna("").astype(str)
        out["expected_qty"] = q
    else:
        out["expected_qty"] = ""
    for c in ["location","sku","pallet_id"]:
        out[c] = out[c].astype(str).str.strip()
    return out.fillna("")

def inv_lookup_expected(location: str, sku: str="", lot: str="", pallet_id: str=""):
    inv = load_cached_inventory()
    if inv.empty or "expected_qty" not in inv.columns: return None
    loc = (location or "").strip(); sku = (sku or "").strip(); pal = (pallet_id or "").strip(); lotN = lot_normalize(lot)
    if loc == "" and pal == "" and sku == "" and lotN == "": return None
    candidates = [
        ({"location":loc, "pallet_id":pal, "lot_number":lotN, "sku":sku}, True),
        ({"location":loc, "pallet_id":pal, "lot_number":lotN}, True),
        ({"location":loc, "pallet_id":pal, "sku":sku}, True),
        ({"location":loc, "pallet_id":pal}, True),
        ({"location":loc, "lot_number":lotN, "sku":sku}, True),
        ({"location":loc, "lot_number":lotN}, True),
        ({"location":loc, "sku":sku}, True),
        ({"location":loc}, True),
    ]
    df = inv
    for cond, _ in candidates:
        tmp = df.copy()
        for k,v in cond.items():
            if v != "":
                tmp = tmp[tmp[k].astype(str).str.strip().str.lower() == str(v).strip().lower()]
        if not tmp.empty:
            for val in tmp["expected_qty"].tolist():
                try: return int(float(val))
                except Exception: continue
    return None

def lock_active(row: pd.Series) -> bool:
    exp = parse_ts(row.get("lock_expires_ts","")); return bool(exp and exp > datetime.now())
def lock_owned_by(row: pd.Series, user: str) -> bool:
    return (row.get("lock_owner","").strip().lower() == (user or "").strip().lower())

def start_or_renew_lock(assignment_id: str, user: str):
    if not assignment_id or not user: return False, "Missing assignment or user"
    df = load_assignments()
    ix = df.index[df["assignment_id"]==assignment_id]
    if len(ix)==0: return False, "Assignment not found"
    i = ix[0]; now = datetime.now(); exp = now + timedelta(minutes=LOCK_MINUTES)
    df.loc[i, "status"] = "In Progress"
    df.loc[i, "lock_owner"] = user.strip()
    df.loc[i, "lock_start_ts"] = now.strftime(TS_FMT)
    df.loc[i, "lock_expires_ts"] = exp.strftime(TS_FMT)
    save_assignments(df)
    return True, f"Locked by {user} until {exp.strftime('%I:%M %p')}"

def validate_lock_for_submit(assignment_id: str, user: str) -> (bool, str):
    if not assignment_id: return True, "Ad-hoc submission"
    df = load_assignments()
    row = df[df["assignment_id"]==assignment_id]
    if row.empty: return True, "Assignment not found; proceeding"
    r = row.iloc[0]
    if not lock_active(r): return True, "Lock expired or not set; proceeding"
    if lock_owned_by(r, user): return True, "Lock valid for user"
    return False, f"Locked by {r.get('lock_owner','?')} until {r.get('lock_expires_ts','?')}"

def focus_by_label(label_text: str):
    if not label_text: return
    components.html(f"""
    <script>
      setTimeout(function(){{
        const labs=[...parent.document.querySelectorAll('label')];
        const lab=labs.find(el=>el.innerText.trim()==="{label_text}".trim());
        if(lab){{
          const inp=lab.parentElement.querySelector('input,textarea');
          if(inp){{ inp.focus(); if(inp.select) inp.select(); }}
        }}
      }}, 150);
    </script>
    """, height=0)

def switch_to_tab(tab_label: str):
    safe = (tab_label or "").lower()
    components.html(f"""
    <script>
      setTimeout(function(){{
        const L = "{safe}";
        const tabs = [
          ...parent.document.querySelectorAll('button[role="tab"]'),
          ...parent.document.querySelectorAll('[data-baseweb="tab"]')
        ];
        const target = tabs.find(el => (el.innerText||'').trim().toLowerCase().includes(L));
        if (target) target.click();
      }}, 150);
    </script>
    """, height=0)

def queue_feedback(kind: str):
    st.session_state["_feedback_kind"] = kind

def emit_feedback():
    enable_sound = st.session_state.get("fb_sound", True)
    enable_vibe  = st.session_state.get("fb_vibe", True)
    kind = st.session_state.pop("_feedback_kind", "")
    if not kind: return
    snd = "true" if enable_sound else "false"
    vib = "true" if enable_vibe else "false"
    nonce = uuid.uuid4().hex
    components.html(f"""
    <script>
    (function(){{
      const enableSound = {snd}, enableVibe = {vib};
      function beep(pattern){{
        try{{
          const ctx = new (window.AudioContext||window.webkitAudioContext)();
          const g = ctx.createGain(); g.gain.value = 0.08; g.connect(ctx.destination);
          let t = ctx.currentTime;
          pattern.forEach(p => {{
            const o = ctx.createOscillator();
            o.type = p.type || 'sine';
            o.frequency.setValueAtTime(p.f, t);
            o.connect(g); o.start(t); o.stop(t + p.d/1000);
            t += (p.d + (p.gap||40))/1000;
          }});
        }}catch(e){{}}
      }}
      function vibrate(seq){{ try{{ if (navigator.vibrate) navigator.vibrate(seq); }}catch(e){{}} }}
      let tone=[], vib=[];
      switch("{kind}"){{
        case "scan":    tone=[{{f:1000,d:60}},{{f:1200,d:60}}]; vib=[40,20,40]; break;
        case "success": tone=[{{f:880,d:120}},{{f:1320,d:120}}]; vib=[70,30,70]; break;
        case "error":   tone=[{{f:220,d:220,type:'square'}},{{f:180,d:180,type:'square'}}]; vib=[200,100,200]; break;
      }}
      if (enableSound && tone.length) beep(tone);
      if (enableVibe && vib.length) vibrate(vib);
    }})(); // {nonce}
    </script>
    """, height=0)

# ✅ Correct name here:
AGGRID_ENABLED = (os.getenv("AGGRID_ENABLED","1") == "1") and _AGGRID_IMPORTED

def show_table(df, height=300, key=None, selectable=False, selection_mode="single", numeric_cols=None):
    if df is None or (hasattr(df, "empty") and df.empty):
        st.info(t("no_data")); return {"selected_rows": []}
    if AGGRID_ENABLED:
        try:
            gob = GridOptionsBuilder.from_dataframe(df)
            gob.configure_default_column(resizable=True, filter=True, sortable=True)
            if selectable: gob.configure_selection(selection_mode, use_checkbox=True)
            if numeric_cols:
                for col in numeric_cols:
                    if col in df.columns: gob.configure_column(col, type=["numericColumn"])
            return AgGrid(df, gridOptions=gob.build(),
                          update_mode=(GridUpdateMode.SELECTION_CHANGED if selectable else GridUpdateMode.NO_UPDATE),
                          height=height, key=key)
        except Exception as e:
            st.warning(f"AgGrid unavailable, falling back to simple table: {e}")
    st.dataframe(df, use_container_width=True, height=height)
    return {"selected_rows": []}

# ---------------- Page layout & defaults ----------------
st.set_page_config(page_title=f"{t('app_name')} {VERSION}", layout="wide")

# First ensure lang default, then header
_ensure_default("lang", _lang_default())
_ensure_default("mobile_mode", True)
_ensure_default("fb_sound", True)
_ensure_default("fb_vibe", True)
_ensure_default("auto_focus", True)
_ensure_default("auto_advance", True)

# Header with language selector
left, right = st.columns([0.7, 0.3])
with left:
    st.title(f"{t('app_name')} ({VERSION})")
with right:
    sel = st.selectbox(t("lang"), [("en", t("lang_en")), ("es", t("lang_es"))],
        index=(0 if st.session_state.get("lang","en")=="en" else 1),
        format_func=lambda x: x[1], key="lang_select")
    if sel[0] != st.session_state.get("lang","en"):
        st.session_state["lang"] = sel[0]; st.rerun()

st.caption(t("tip_submit_once"))
st.caption(f"{t('active_dir')}: {PATHS['root']} · {t('tz')}: {TZ_LABEL} · {t('lock')}: {LOCK_MINUTES} {t('minutes')}")

TAB_LABELS = [t("tab_assign"), t("tab_my"), t("tab_perform"), t("tab_dash"), t("tab_disc"), t("tab_settings")]
tabs = st.tabs(TAB_LABELS)

# -------- Assign Counts
with tabs[0]:
    st.subheader(t("assign_title"))
    c_top1, c_top2 = st.columns(2)
    with c_top1:
        assigned_by = st.text_input(t("assigned_by"), value=st.session_state.get("assigned_by",""), key="assign_assigned_by")
    with c_top2:
        assignee = st.text_input(t("assign_to"), value=st.session_state.get("assignee",""), key="assign_assignee")

    inv_df = load_cached_inventory()
    loc_options = []
    if inv_df is not None and hasattr(inv_df, "empty") and not inv_df.empty and "location" in inv_df.columns:
        loc_options = sorted(inv_df["location"].astype(str).str.strip().replace("nan","").dropna().unique().tolist())

    st.caption(t("hint_assign"))
    colL, _ = st.columns([1.2, 1])
    with colL:
        selected_locs = st.multiselect(t("locations"), options=loc_options, default=[], help="", key="assign_locations_multiselect")
        pasted = st.text_area(t("paste_locs"), value="", height=120, key="assign_locations_paste", placeholder="e.g.\n11400804\n11400805\nTUN01001")
        pasted_list = [ln.strip() for ln in pasted.splitlines() if ln.strip()] if pasted else []
        seen = set(); loc_merge = []
        for s in selected_locs + pasted_list:
            if s not in seen:
                loc_merge.append(s); seen.add(s)
        notes = st.text_area(t("notes"), value="", height=80, key="assign_notes")
        disabled = (not assigned_by) or (not assignee) or (len(loc_merge) == 0)
        if st.button(t("create_assign"), type="primary", disabled=disabled, key="assign_create_btn", use_container_width=True):
            dfA = load_assignments()
            created = 0; dup_conflicts = []; locked_conflicts = []; not_in_cache = []
            def _any_lock_active_for(loc):
                if dfA is None or dfA.empty: return False
                try: same = dfA[dfA["location"].astype(str).str.strip().str.lower() == str(loc).strip().lower()]
                except Exception: return False
                for _, r in same.iterrows():
                    if lock_active(r): return True
                return False
            for loc in loc_merge:
                if not inv_df.empty:
                    if str(loc).strip() not in set(inv_df["location"].astype(str).str.strip().tolist()):
                        not_in_cache.append(str(loc).strip())
                is_dup = False
                if dfA is not None and not dfA.empty:
                    cand = dfA[(dfA["location"].astype(str).str.strip().str.lower() == str(loc).strip().lower()) & (dfA["status"].isin(["Assigned","In Progress"]))]
                    is_dup = not cand.empty
                if is_dup: dup_conflicts.append(loc); continue
                if _any_lock_active_for(loc): locked_conflicts.append(loc); continue
                sku = lot_num = pallet = expected = ""
                try:
                    cand_inv = inv_df[inv_df["location"].astype(str).str.strip().str.lower() == str(loc).strip().lower()] if (inv_df is not None and not inv_df.empty) else None
                    if cand_inv is not None and not cand_inv.empty:
                        r = cand_inv.iloc[0]
                        sku = str(r.get("sku","")); lot_num = lot_normalize(r.get("lot_number","")); pallet = str(r.get("pallet_id",""))
                        expected_val = r.get("expected_qty","")
                        try: expected = str(int(float(expected_val))) if str(expected_val) != "" else ""
                        except Exception: expected = str(expected_val) if str(expected_val) != "" else ""
                except Exception: pass
                row = {
                    "assignment_id": mk_id("CC"),
                    "assigned_by": assigned_by.strip(),
                    "assignee": assignee.strip(),
                    "location": str(loc).strip(),
                    "sku": sku, "lot_number": lot_num, "pallet_id": pallet,
                    "expected_qty": expected, "priority": "Normal", "status": "Assigned",
                    "created_ts": now_str(), "due_date": "", "notes": notes.strip(),
                    "lock_owner": "", "lock_start_ts": "", "lock_expires_ts": ""
                }
                safe_append_csv(PATHS["assign"], row, ASSIGN_COLS)
                created += 1
            st.session_state["assigned_by"] = assigned_by
            st.session_state["assignee"] = assignee
            if created > 0: st.success(t("created_n", n=created, name=assignee)); queue_feedback("success")
            if dup_conflicts:
                sample = ", ".join(map(str, dup_conflicts[:10])) + ("…" if len(dup_conflicts)>10 else "")
                st.warning(t("dup_skipped", n=len(dup_conflicts), sample=sample))
            if locked_conflicts:
                st.warning(t("locked_skipped", n=len(locked_conflicts)))
            if not_in_cache:
                sample = ", ".join(map(str, not_in_cache[:10])) + ("…" if len(not_in_cache)>10 else "")
                st.info(t("not_in_cache", n=len(not_in_cache), sample=sample))

    dfA = load_assignments()
    if not dfA.empty:
        def _lock_info(r):
            if lock_active(r):
                who = r.get("lock_owner","?"); until = r.get("lock_expires_ts","")
                return t("locked_by_until", who=who, until=until)
            return t("available")
        dfA_disp = dfA.copy(); dfA_disp["lock_info"] = dfA_disp.apply(_lock_info, axis=1)
        st.write(t("all_assign"))
        show_table(dfA_disp, height=300, key="grid_all_assign")
    else:
        st.info(t("no_assign"))

# -------- My Assignments
with tabs[1]:
    st.subheader(t("my_title"))
    me = st.text_input(t("i_am"), key="me_name", value=st.session_state.get("assignee",""))

    dfA = load_assignments()
    mine = dfA[dfA["assignee"].str.lower() == (me or "").lower()] if me else dfA.iloc[0:0]

    cA, cB, cC, cD = st.columns(4)
    cA.metric(t("open"), int((mine["status"]=="Assigned").sum()))
    cB.metric(t("in_progress"), int((mine["status"]=="In Progress").sum()))
    cC.metric(t("submitted"), int((mine["status"]=="Submitted").sum()))
    cD.metric(t("total"), int(len(mine)))

    st.write(t("your_assign"))
    selected_dict = None

    if not mine.empty:
        if AGGRID_ENABLED:
            def _lock_info2(r):
                if lock_active(r):
                    who = r.get("lock_owner","?"); until = r.get("lock_expires_ts","")
                    you = "You" if st.session_state.get("lang","en")=="en" else "Tú"
                    who_disp = you if (who or "").lower()==(me or "").lower() else who
                    return t("locked_by_until", who=who_disp, until=until)
                return t("available")
            mine_disp = mine.copy()
            mine_disp["lock_info"] = mine_disp.apply(_lock_info2, axis=1)
            res = show_table(mine_disp, height=300, key="grid_my_assign", selectable=True, selection_mode="single")
            sel = res.get("selected_rows", [])
            if isinstance(sel, pd.DataFrame): srec = sel.to_dict(orient="records")
            elif isinstance(sel, list):       srec = sel
            else:
                try: srec = list(sel)
                except Exception: srec = []
            if srec: selected_dict = srec[0]
        else:
            opts = []
            for _, r in mine.iterrows():
                label = f"{r.get('assignment_id','')} — {r.get('location','')} — {r.get('status','')}"
                opts.append((label, r.get("assignment_id","")))
            if opts:
                def _fmt(val):
                    for lbl, v in opts:
                        if v == val: return lbl
                    return val
                choice = st.radio(t("radio_label"), [v for _, v in opts], format_func=_fmt, key="my_assign_choice")
                if choice: selected_dict = mine[mine["assignment_id"]==choice].iloc[0].to_dict()

        if selected_dict: st.session_state["pending_assignment"] = selected_dict

        pending = st.session_state.get("pending_assignment")
        if pending:
            st.markdown(t("selected_summary", id=pending.get('assignment_id',''), loc=pending.get('location',''), status=pending.get('status','')))
            if st.button(t("submit_assignment"), type="primary", key="my_submit_assignment_btn", use_container_width=True):
                assign_id = pending.get("assignment_id","")
                if not me:
                    st.error(t("err_enter_name")); queue_feedback("error")
                else:
                    dfA2 = load_assignments()
                    row = dfA2[dfA2["assignment_id"]==assign_id]
                    if row.empty:
                        st.error(t("err_missing")); queue_feedback("error")
                    else:
                        r = row.iloc[0]
                        if str(r.get("assignee","")).strip().lower() != str(me).strip().lower():
                            st.error(t("err_belongs_to", assignee=r.get('assignee','?'))); queue_feedback("error")
                        elif str(r.get("status","")).strip() == "Submitted":
                            st.error(t("err_already_submitted")); queue_feedback("error")
                        elif lock_active(r) and not lock_owned_by(r, me):
                            st.error(t("err_locked_other", who=r.get('lock_owner','?'), until=r.get('lock_expires_ts','?'))); queue_feedback("error")
                        else:
                            ok, msg = start_or_renew_lock(assign_id, me)
                            if not ok:
                                st.error(msg); queue_feedback("error")
                            else:
                                st.session_state["current_assignment"] = r.to_dict()
                                st.success(t("lock_success_opening", msg=msg)); queue_feedback("success")
                                switch_to_tab(t("tab_perform"))
    else:
        st.info(t("no_assign"))
    emit_feedback()

# -------- Perform Count (locked fields except Counted QTY + Note)
with tabs[2]:
    st.subheader(t("perform_title"))

    t1, t2 = st.columns(2)
    with t1: st.checkbox(t("auto_focus_loc"), key="auto_focus")
    with t2: st.checkbox(t("auto_advance"), key="auto_advance")
    auto_focus  = st.session_state.get("auto_focus", True)
    auto_advance= st.session_state.get("auto_advance", True)

    def _hydrate_from_current(cur: dict):
        exp_raw = cur.get("expected_qty","")
        try: exp_int = int(float(exp_raw)) if str(exp_raw).strip() != "" else 0
        except Exception: exp_int = 0
        st.session_state.update({
            "perform_assignment_id": cur.get("assignment_id",""),
            "perform_assignee": cur.get("assignee", st.session_state.get("me_name","")),
            "perform_location": cur.get("location",""),
            "perform_pallet":   cur.get("pallet_id",""),
            "perform_sku":      cur.get("sku",""),
            "perform_lot":      cur.get("lot_number",""),
            "perform_expected": exp_int,
            "perform_counted_str": st.session_state.get("perform_counted_str",""),
        })

    cur = st.session_state.get("current_assignment", {})
    selected_id = cur.get("assignment_id", "")
    loaded_from = st.session_state.get("_perform_loaded_from", "")
    if selected_id and selected_id != loaded_from:
        _hydrate_from_current(cur)
        st.session_state["_perform_loaded_from"] = selected_id
    if cur and not st.session_state.get("perform_assignment_id"):
        _hydrate_from_current(cur)
        if selected_id: st.session_state["_perform_loaded_from"] = selected_id

    assignment_id = st.text_input(t("assignment_id"), key="perform_assignment_id", disabled=True)
    assignee      = st.text_input(t("assignee"), key="perform_assignee", disabled=True)

    c1, c2 = st.columns(2)
    with c1:
        location = st.text_input(t("scan_location"), key="perform_location", disabled=True)
    with c2:
        pallet   = st.text_input(t("scan_pallet"), key="perform_pallet", disabled=True)

    c3, c4, c5 = st.columns(3)
    with c3:
        sku = st.text_input(t("sku"), key="perform_sku", disabled=True)
    with c4:
        lot = st.text_input(t("lot"), key="perform_lot", disabled=True)
    with c5:
        expected_num = st.number_input(t("expected_qty"), min_value=0, key="perform_expected", disabled=True)

    counted_str = st.text_input(t("counted_qty"), placeholder="", key="perform_counted_str")
    note = st.text_input(t("note"), key="perform_note")

    if auto_focus and not st.session_state.get("_did_autofocus"):
        focus_by_label(t("counted_qty")); st.session_state["_did_autofocus"] = True

    def _parse_count(s):
        s = (s or "").strip()
        if s == "": return None
        if not re.fullmatch(r"\d+", s): return "invalid"
        return int(s)

    def _handle_submit():
        assignment_id = st.session_state.get("perform_assignment_id","")
        assignee      = st.session_state.get("perform_assignee","")
        location      = st.session_state.get("perform_location","")
        pallet        = st.session_state.get("perform_pallet","")
        sku           = st.session_state.get("perform_sku","")
        lot           = st.session_state.get("perform_lot","")
        note          = st.session_state.get("perform_note","")
        counted_str   = st.session_state.get("perform_counted_str","")
        counted_val   = _parse_count(counted_str)
        expected_num  = st.session_state.get("perform_expected", 0)

        if not assignee or not location:
            st.session_state["_submit_msg"] = ("warn", t("warn_need_fields")); return
        if counted_val in (None, "invalid"):
            st.session_state["_submit_msg"] = ("warn", t("warn_count_invalid")); return

        ok, why = validate_lock_for_submit(assignment_id, assignee)
        if not ok:
            st.session_state["_submit_msg"] = ("error", str(why)); return

        variance = counted_val - expected_num if expected_num is not None else ""
        row = {
            "submission_id": mk_id("CCS"),
            "assignment_id": assignment_id or "",
            "assignee": assignee.strip(),
            "location": location.strip(),
            "sku": sku.strip(),
            "lot_number": lot_normalize(lot),
            "pallet_id": pallet.strip(),
            "counted_qty": int(counted_val),
            "expected_qty": int(expected_num) if expected_num is not None else "",
            "variance": variance if variance != "" else "",
            "variance_flag": ("Over" if variance>0 else ("Short" if variance<0 else "Match")),
            "timestamp": now_str(),
            "device_id": "",
            "note": (note or "").strip(),
        }
        safe_append_csv(PATHS["subs"], row, SUBMIT_COLS)

        dfA2 = load_assignments()
        if assignment_id and not dfA2.empty:
            ix = dfA2.index[dfA2["assignment_id"]==assignment_id]
            if len(ix)>0:
                dfA2.loc[ix, "status"] = "Submitted"
                dfA2.loc[ix, ["lock_owner","lock_start_ts","lock_expires_ts"]] = ["","",""]
                save_assignments(dfA2)

        st.session_state["_submit_msg"] = ("success", t("submitted_ok"))
        st.session_state["perform_counted_str"] = ""
        queue_feedback("success")

    st.button(t("submit_count"), type="primary", key="perform_submit_btn", use_container_width=True, on_click=_handle_submit)

    msg = st.session_state.pop("_submit_msg", None)
    if msg:
        level, text = msg
        if level=="success": st.success(text)
        elif level=="warn":  st.warning(text)
        else:                st.error(text)
        st.rerun()

    emit_feedback()

# -------- Dashboard (Live)
with tabs[3]:
    st.subheader(t("dash_title"))
    subs_path = PATHS["subs"]
    refresh_sec = st.slider(t("auto_refresh_sec"), 2, 30, 5, key="dash_refresh")
    st.caption(f"{t('subs_file')}: {subs_path}")
    dfS = load_submissions()
    dfS_disp = dfS.copy()
    if st.session_state.get("mobile_mode", True) and not dfS_disp.empty:
        keep = [c for c in ["timestamp","assignee","location","counted_qty","expected_qty","variance","variance_flag"] if c in dfS_disp.columns]
        if keep: dfS_disp = dfS_disp[keep]
    today_str = datetime.now().strftime("%m/%d/%Y")
    today_df = dfS[dfS["timestamp"].str.contains(today_str)] if not dfS.empty else dfS
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(t("counts_today"), int(len(today_df)))
    c2.metric(t("over"),  int((today_df["variance_flag"]=="Over").sum()) if not today_df.empty else 0)
    c3.metric(t("short"), int((today_df["variance_flag"]=="Short").sum()) if not today_df.empty else 0)
    c4.metric(t("match"), int((today_df["variance_flag"]=="Match").sum()) if not today_df.empty else 0)
    st.write(t("latest_subs"))
    show_table(dfS_disp, height=320, key="grid_submissions", numeric_cols=["variance"])
    last_mod = os.path.getmtime(subs_path) if os.path.exists(subs_path) else 0
    time.sleep(refresh_sec)
    if os.path.exists(subs_path) and os.path.getmtime(subs_path) != last_mod:
        st.rerun()

# -------- Discrepancies
with tabs[4]:
    st.subheader(t("disc_title"))
    dfS = load_submissions()
    ex = dfS[dfS["variance_flag"].isin(["Over","Short"])]
    ex_disp = ex.copy()
    if st.session_state.get("mobile_mode", True) and not ex_disp.empty:
        keep = [c for c in ["timestamp","assignee","location","counted_qty","expected_qty","variance","variance_flag","note"] if c in ex_disp.columns]
        if keep: ex_disp = ex_disp[keep]
    st.write(t("exceptions"))
    show_table(ex_disp, height=300, key="grid_exceptions", numeric_cols=["variance"])
    st.download_button(t("export_ex"), data=ex.to_csv(index=False), file_name="cyclecount_exceptions.csv", mime="text/csv", key="disc_export_btn")

# -------- Settings
with tabs[5]:
    st.subheader(t("settings_title"))
    st.write(t("env_vars"))
    st.code("""CYCLE_COUNT_LOG_DIR=<shared path>
BIN_HELPER_LOG_DIR=<fallback if set>
CC_LOCK_MINUTES=<default 20>
AGGRID_ENABLED=<1 or 0>
CC_LANG=<en|es>""", language="bash")
    st.caption(t("tip_dir"))
    st.write(t("active_paths"), PATHS)
    st.divider()
    st.markdown(f"### {t('inv_upload_title')}")
    inv_df_cached = load_cached_inventory()
    if not inv_df_cached.empty:
        st.success(t("inv_cache_loaded", n=f"{len(inv_df_cached):,}"))
        st.dataframe(inv_df_cached.head(10), use_container_width=True)
    upload = st.file_uploader("Upload Inventory Excel (.xlsx/.xls/.csv)", type=["xlsx","xls","csv"], key="settings_upload_inv")
    if upload is not None:
        try:
            name = getattr(upload, "name", "") or ""
            ext = (name.lower().split(".")[-1] if "." in name else "")
            if ext == "csv":
                raw = read_csv_fallback(upload, dtype=str).fillna("")
                st.write(t("preview_first10")); st.dataframe(raw.head(10), use_container_width=True)
            else:
                engine = "openpyxl" if ext == "xlsx" else "xlrd"
                xls = pd.ExcelFile(upload, engine=engine)
                sheet = st.selectbox("Select sheet", xls.sheet_names, index=0, key="settings_sheet")
                raw = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
                st.write(t("preview_first10")); st.dataframe(raw.head(10), use_container_width=True)
            mapping_saved = load_inventory_mapping() or {}
            mapping_session = st.session_state.get("map_defaults", {})
            base_map = {**DEFAULT_MAPPING, **mapping_session, **mapping_saved}
            cols = list(raw.columns)
            st.markdown(f"#### {t('column_mapping')}")
            def idx_for(colname): return (cols.index(colname)+1) if (colname in cols and colname) else 0
            c1,c2,c3,c4,c5 = st.columns(5)
            with c1: loc_col = st.selectbox(t("map_loc"), ["<none>"]+cols, index=idx_for(base_map.get("location","")), key="map_loc")
            with c2: sku_col = st.selectbox(t("map_sku"), ["<none>"]+cols, index=idx_for(base_map.get("sku","")), key="map_sku")
            with c3: lot_col = st.selectbox(t("map_lot"), ["<none>"]+cols, index=idx_for(base_map.get("lot_number","")), key="map_lot")
            with c4: pal_col = st.selectbox(t("map_pal"), ["<none>"]+cols, index=idx_for(base_map.get("pallet_id","")), key="map_pal")
            with c5: qty_col = st.selectbox(t("map_qty"), ["<none>"]+cols, index=idx_for(base_map.get("expected_qty","")), key="map_qty")
            current_map = {
                "location":   (st.session_state.get("map_loc") if st.session_state.get("map_loc")   and st.session_state.get("map_loc")!="<none>" else ""),
                "sku":        (st.session_state.get("map_sku") if st.session_state.get("map_sku")   and st.session_state.get("map_sku")!="<none>" else ""),
                "lot_number": (st.session_state.get("map_lot") if st.session_state.get("map_lot")   and st.session_state.get("map_lot")!="<none>" else ""),
                "pallet_id":  (st.session_state.get("map_pal") if st.session_state.get("map_pal")   and st.session_state.get("map_pal")!="<none>" else ""),
                "expected_qty":(st.session_state.get("map_qty") if st.session_state.get("map_qty")  and st.session_state.get("map_qty")!="<none>" else ""),
            }
            st.session_state["map_defaults"] = current_map
            if st.button(t("save_map"), type="primary", key="map_save_btn"):
                norm = normalize_inventory_df(raw, current_map)
                save_inventory_cache(norm); save_inventory_mapping(current_map)
                st.success(f"Saved mapping and cached {len(norm):,} rows."); st.rerun()
        except Exception as e:
            st.warning(t("excel_err", err=e))
