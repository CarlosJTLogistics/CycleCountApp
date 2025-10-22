# v1.4.0 (encoding fallback for CSV; baked-in default mapping; Supervisor Tools removed; debounce fix; session mapping memory)
import os, time, uuid, re, json
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Try to import AgGrid; fall back gracefully if not available
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    _AGGRID_IMPORTED = True
except Exception:
    _AGGRID_IMPORTED = False

APP_NAME = "Cycle Counting"
VERSION = "v1.4.0 (encoding fix + default mapping)"
TZ_LABEL = "US/Central"
LOCK_MINUTES_DEFAULT = 20
LOCK_MINUTES = int(os.getenv("CC_LOCK_MINUTES", LOCK_MINUTES_DEFAULT))
TS_FMT = "%m/%d/%Y %I:%M:%S %p"

# ---------- Defaults (requested by Carlos)
DEFAULT_MAPPING = {
    "location": "Location Name",
    "sku": "WarehouseSKU",
    "lot_number": "CustomerLotReference",
    "pallet_id": "PalletID",
    "expected_qty": "QTY Available",
}

def lot_normalize(x: str) -> str:
    if x is None or (isinstance(x,float) and pd.isna(x)): return ""
    s = re.sub(r"\D", "", str(x))
    s = re.sub(r"^0+", "", s)
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

# Keep 'device_id' column for CSV schema compatibility (we write it as empty "")
SUBMIT_COLS = [
    "submission_id","assignment_id","assignee","location","sku","lot_number","pallet_id",
    "counted_qty","expected_qty","variance","variance_flag","timestamp","device_id","note"
]

# ---------- CSV helpers (encoding fallback)
_ENCODINGS = ["utf-8", "cp1252", "latin-1"]

def read_csv_fallback(fp, dtype=str):
    last_err = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(fp, dtype=dtype, encoding=enc).fillna("")
        except Exception as e:
            last_err = e
            continue
    # If still failing, try errors='replace' with latin-1
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
        with open(tmp, "a", encoding="utf-8") as f:
            df.to_csv(f, header=False, index=False)
        with open(tmp, "rb") as fin, open(path, "ab") as fout:
            fout.write(fin.read())
        os.remove(tmp)
    else:
        df.to_csv(path, index=False, encoding="utf-8")

def read_csv_locked(path, columns=None):
    if not os.path.exists(path): return pd.DataFrame(columns=columns or [])
    for _ in range(5):
        try:
            return read_csv_fallback(path, dtype=str)
        except Exception:
            time.sleep(0.1)
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

# ---------- Inventory cache & mapping
def load_cached_inventory() -> pd.DataFrame:
    if "inv_df" in st.session_state:
        return st.session_state["inv_df"]
    if os.path.exists(PATHS["inv_csv"]):
        try:
            inv = read_csv_fallback(PATHS["inv_csv"], dtype=str).fillna("")
            st.session_state["inv_df"] = inv
            return inv
        except Exception:
            pass
    return pd.DataFrame(columns=["location","sku","lot_number","pallet_id","expected_qty"])

def save_inventory_cache(df: pd.DataFrame):
    dataframe_to_csv_utf8(df, PATHS["inv_csv"])
    st.session_state["inv_df"] = df

def save_inventory_mapping(mapping: dict):
    with open(PATHS["inv_map"], "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

def load_inventory_mapping() -> dict:
    if os.path.exists(PATHS["inv_map"]):
        try:
            return json.load(open(PATHS["inv_map"], "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}

def normalize_inventory_df(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = pd.DataFrame()
    out["location"]   = df[mapping.get("location","")].astype(str)    if mapping.get("location","")    in df.columns else ""
    out["sku"]        = df[mapping.get("sku","")].astype(str)         if mapping.get("sku","")         in df.columns else ""
    lot_col = mapping.get("lot_number","")
    out["lot_number"] = df[lot_col].astype(str).map(lot_normalize)    if lot_col                        in df.columns else ""
    out["pallet_id"]  = df[mapping.get("pallet_id","")].astype(str)   if mapping.get("pallet_id","")   in df.columns else ""
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
    loc = (location or "").strip()
    sku = (sku or "").strip()
    pal = (pallet_id or "").strip()
    lotN = lot_normalize(lot)
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
                try:
                    return int(float(val))
                except Exception:
                    continue
    return None

def lock_active(row: pd.Series) -> bool:
    exp = parse_ts(row.get("lock_expires_ts",""))
    return bool(exp and exp > datetime.now())

def lock_owned_by(row: pd.Series, user: str) -> bool:
    return (row.get("lock_owner","").strip().lower() == (user or "").strip().lower())

def start_or_renew_lock(assignment_id: str, user: str):
    if not assignment_id or not user: return False, "Missing assignment or user"
    df = load_assignments()
    ix = df.index[df["assignment_id"]==assignment_id]
    if len(ix)==0: return False, "Assignment not found"
    i = ix[0]
    now = datetime.now()
    exp = now + timedelta(minutes=LOCK_MINUTES)
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

# -------- UI helpers (mobile, haptics, sound)
def inject_mobile_css(scale: float = 1.2):
    base_px = int(16 * scale)
    st.markdown(f"""
        <style>
        .stTextInput input, .stNumberInput input {{ font-size: {base_px}px !important; padding: 12px 14px !important; }}
        .stButton > button {{ font-size: {base_px}px !important; padding: 12px 16px !important; width: 100% !important; }}
        .stSelectbox, .stMultiselect, .stTextArea textarea {{ font-size: {base_px}px !important; }}
        </style>
    """, unsafe_allow_html=True)

def focus_by_label(label_text: str):
    if not label_text: return
    components.html(f"""
        <script>
        setTimeout(function(){{{{ 
            const labs=[...parent.document.querySelectorAll('label')];
            const lab=labs.find(el=>el.innerText.trim()==="{label_text}".trim());
            if(lab){{{{ 
                const inp=lab.parentElement.querySelector('input,textarea');
                if(inp){{{{ inp.focus(); if(inp.select) inp.select(); }}}}
            }}}}
        }}}}, 150);
        </script>
    """, height=0)

def queue_feedback(kind: str):
    st.session_state["_feedback_kind"] = kind

def emit_feedback():
    enable_sound = st.session_state.get("fb_sound", True)
    enable_vibe = st.session_state.get("fb_vibe", True)
    kind = st.session_state.pop("_feedback_kind", "")
    if not kind: return
    snd = "true" if enable_sound else "false"
    vib = "true" if enable_vibe else "false"
    nonce = uuid.uuid4().hex
    components.html(f"""
        <script>
        (function(){{{{ 
            const enableSound = {snd}, enableVibe = {vib};
            function beep(pattern){{{{ 
                try{{{{ 
                    const ctx = new (window.AudioContext||window.webkitAudioContext)();
                    const g = ctx.createGain(); g.gain.value = 0.08; g.connect(ctx.destination);
                    let t = ctx.currentTime;
                    pattern.forEach(p => {{{{ 
                        const o = ctx.createOscillator();
                        o.type = p.type || 'sine';
                        o.frequency.setValueAtTime(p.f, t);
                        o.connect(g); o.start(t); o.stop(t + p.d/1000);
                        t += (p.d + (p.gap||40))/1000;
                    }}}});
                }}}} catch(e){{{{}}}}
            }}}}
            function vibrate(seq){{{{ try{{{{ if (navigator.vibrate) navigator.vibrate(seq); }}}} catch(e){{{{}}}} }}}}
            let tone=[], vib=[];
            switch("{kind}"){{{{ 
                case "scan": tone=[{{{{f:1000,d:60}}}},{{{{f:1200,d:60}}}}]; vib=[40,20,40]; break;
                case "success": tone=[{{{{f:880,d:120}}}},{{{{f:1320,d:120}}}}]; vib=[70,30,70]; break;
                case "error": tone=[{{{{f:220,d:220,type:'square'}}}},{{{{f:180,d:180,type:'square'}}}}]; vib=[200,100,200]; break;
            }}}}
            if (enableSound && tone.length) beep(tone);
            if (enableVibe && vib.length) vibrate(vib);
        }}}})(); // {nonce}
        </script>
    """, height=0)

AGGRID_ENABLED = (os.getenv("AGGRID_ENABLED","1") == "1") and _AGGRID_IMPORTED

def show_table(df, height=300, key=None, selectable=False, selection_mode="single", numeric_cols=None):
    if df is None or (hasattr(df, "empty") and df.empty):
        st.info("No data"); return {"selected_rows": []}
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

st.set_page_config(page_title=f"{APP_NAME} {VERSION}", layout="wide")
st.title(f"{APP_NAME} ({VERSION})")

def _ensure_default(k, v):
    if k not in st.session_state: st.session_state[k] = v
_ensure_default("mobile_mode", True)
_ensure_default("fb_sound", True)
_ensure_default("fb_vibe", True)
_ensure_default("auto_focus", True)
_ensure_default("auto_advance", True)
_ensure_default("auto_submit", False)

# ---------------- Session-only mapping helpers ----------------
def _get_session_mapping():
    return st.session_state.get("map_defaults", {})

def _set_session_mapping(mapping: dict):
    st.session_state["map_defaults"] = {
        "location": mapping.get("location",""),
        "sku": mapping.get("sku",""),
        "lot_number": mapping.get("lot_number",""),
        "pallet_id": mapping.get("pallet_id",""),
        "expected_qty": mapping.get("expected_qty",""),
    }

st.caption("Tip: Select an assignment once. We load it without looping; re-select a different row to change.")

st.caption(f"Active log dir: {PATHS['root']} · Timezone: {TZ_LABEL} · Lock: {LOCK_MINUTES} min")

# Tabs (Supervisor Tools removed)
tabs = st.tabs(["Assign Counts","My Assignments","Perform Count","Dashboard (Live)","Discrepancies","Settings"])

# ---------- Assign Counts
with tabs[0]:
    st.subheader("Assign Counts")
    c_top1, c_top2 = st.columns(2)
    with c_top1:
        assigned_by = st.text_input("Assigned by", value=st.session_state.get("assigned_by",""), key="assign_assigned_by")
    with c_top2:
        assignee = st.text_input("Assign to (name)", value=st.session_state.get("assignee",""), key="assign_assignee")

    inv_df = load_cached_inventory()
    loc_options = []
    if inv_df is not None and hasattr(inv_df, "empty") and not inv_df.empty and "location" in inv_df.columns:
        loc_options = sorted(inv_df["location"].astype(str).str.strip().replace("nan","").dropna().unique().tolist())

    st.caption("Select multiple locations and/or paste a list. Other fields auto-fill from the inventory cache.")
    colL, colR = st.columns([1.2, 1])
    with colL:
        selected_locs = st.multiselect("Locations", options=loc_options, default=[], help="Search and pick multiple.", key="assign_locations_multiselect")
        pasted = st.text_area("Paste locations (optional)", value="", height=120, key="assign_locations_paste", placeholder="e.g.\n11400804\n11400805\nTUN01001")
        pasted_list = [ln.strip() for ln in pasted.splitlines() if ln.strip()] if pasted else []
        seen = set(); loc_merge = []
        for s in selected_locs + pasted_list:
            if s not in seen:
                loc_merge.append(s); seen.add(s)
        notes = st.text_area("Notes (optional)", value="", height=80, key="assign_notes", placeholder="Any special instructions for the counter...")
        disabled = (not assigned_by) or (not assignee) or (len(loc_merge) == 0)
        if st.button("Create Assignments", type="primary", disabled=disabled, key="assign_create_btn", use_container_width=True):
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
            if created > 0: st.success(f"Created {created} assignment(s) for {assignee}."); queue_feedback("success")
            if dup_conflicts: st.warning(f"Skipped {len(dup_conflicts)} duplicate location(s) already Assigned/In Progress: {', '.join(map(str, dup_conflicts[:10]))}{'…' if len(dup_conflicts)>10 else ''}")
            if locked_conflicts: st.warning(f"Skipped {len(locked_conflicts)} location(s) currently locked by another user.")
            if not_in_cache: st.info(f"{len(not_in_cache)} location(s) not in inventory cache (FYI): {', '.join(map(str, not_in_cache[:10]))}{'…' if len(not_in_cache)>10 else ''}")

    st.divider()
    dfA = load_assignments()
    if not dfA.empty:
        def _lock_info(r):
            if lock_active(r):
                who = r.get("lock_owner","?"); until = r.get("lock_expires_ts","")
                return f"🔒 {who} until {until}"
            return "Available"
        dfA_disp = dfA.copy(); dfA_disp["lock_info"] = dfA_disp.apply(_lock_info, axis=1)
        st.write("All Assignments")
        show_table(dfA_disp, height=300, key="grid_all_assign")
    else:
        st.info("No assignments yet.")

# ---------- My Assignments (with debounce to avoid loops)
with tabs[1]:
    st.subheader("My Assignments")
    me = st.text_input("I am (name)", key="me_name", value=st.session_state.get("assignee",""))
    dfA = load_assignments()
    mine = dfA[dfA["assignee"].str.lower() == (me or "").lower()] if me else dfA.iloc[0:0]
    cA, cB, cC, cD = st.columns(4)
    cA.metric("Open", int((mine["status"]=="Assigned").sum()))
    cB.metric("In Progress", int((mine["status"]=="In Progress").sum()))
    cC.metric("Submitted", int((mine["status"]=="Submitted").sum()))
    cD.metric("Total", int(len(mine)))
    st.write("Your Assignments")
    if not mine.empty:
        if AGGRID_ENABLED:
            def _lock_info2(r):
                if lock_active(r):
                    who = r.get("lock_owner","?"); until = r.get("lock_expires_ts","")
                    return f"🔒 {'You' if (who or '').lower()==(me or '').lower() else who} until {until}"
                return "Available"
            mine_disp = mine.copy()
            mine_disp["lock_info"] = mine_disp.apply(_lock_info2, axis=1)
            res = show_table(mine_disp, height=300, key="grid_my_assign", selectable=True, selection_mode="single")
            sel = res.get("selected_rows", [])
            if isinstance(sel, pd.DataFrame):
                sel_records = sel.to_dict(orient="records")
            elif isinstance(sel, list):
                sel_records = sel
            else:
                try: sel_records = list(sel)
                except Exception: sel_records = []
            if len(sel_records) > 0:
                selected = sel_records[0]
                selected_id = selected.get("assignment_id", "")
                last_id = st.session_state.get("_last_loaded_assignment_id", "")
                if selected_id and selected_id != last_id:
                    st.session_state["current_assignment"] = selected
                    st.session_state["_last_loaded_assignment_id"] = selected_id
                    st.rerun()
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
                choice = st.radio("Select an assignment", [v for _, v in opts], format_func=_fmt, key="my_assign_choice")
                if choice:
                    selected = mine[mine["assignment_id"]==choice].iloc[0].to_dict()
                    selected_id = selected.get("assignment_id", "")
                    last_id = st.session_state.get("_last_loaded_assignment_id", "")
                    if selected_id and selected_id != last_id:
                        st.session_state["current_assignment"] = selected
                        st.session_state["_last_loaded_assignment_id"] = selected_id
                        st.rerun()
    else:
        st.info("No assignments found for you.")
    emit_feedback()

# ---------- Perform Count
with tabs[2]:
    st.subheader("Perform Count")
    t1, t2, t3 = st.columns(3)
    with t1: st.checkbox("Auto-focus Location", key="auto_focus")
    with t2: st.checkbox("Auto-advance after scan", key="auto_advance")
    with t3: st.checkbox("Auto-submit after Counted", key="auto_submit")

    auto_focus = st.session_state.get("auto_focus", True)
    auto_advance= st.session_state.get("auto_advance", True)
    auto_submit = st.session_state.get("auto_submit", False)

    cur = st.session_state.get("current_assignment", {})
    assignment_id = st.text_input("Assignment ID", value=cur.get("assignment_id",""), key="perform_assignment_id")
    assignee = st.text_input("Assignee", value=cur.get("assignee", st.session_state.get("me_name","")), key="perform_assignee")

    def _on_loc_change():
        st.session_state["_focus_target_label"] = "Scan Pallet ID (optional)" if (st.session_state.get("perform_pallet","")== "") else "Counted QTY"
        queue_feedback("scan")

    def _on_pallet_change():
        st.session_state["_focus_target_label"] = "Counted QTY"; queue_feedback("scan")

    def _on_count_change():
        st.session_state["_auto_submit_try"] = True

    c1, c2 = st.columns(2)
    with c1:
        location = st.text_input("Scan Location", value=cur.get("location",""), placeholder="Scan or type location", key="perform_location", on_change=_on_loc_change)
    with c2:
        pallet = st.text_input("Scan Pallet ID (optional)", value=cur.get("pallet_id",""), placeholder="Scan pallet ID", key="perform_pallet", on_change=_on_pallet_change)

    c3, c4, c5 = st.columns(3)
    with c3:
        sku = st.text_input("SKU (optional)", value=cur.get("sku",""), key="perform_sku")
    with c4:
        lot = st.text_input("LOT Number (optional)", value=cur.get("lot_number",""), key="perform_lot")

    auto_expected = inv_lookup_expected(location, sku, lot, pallet)
    cur_exp = cur.get("expected_qty","")
    try_cur_exp = int(cur_exp) if str(cur_exp).isdigit() else None
    default_expected = auto_expected if auto_expected is not None else (try_cur_exp if try_cur_exp is not None else 0)
    with c5:
        expected_num = st.number_input("Expected QTY (auto from Inventory if available)", min_value=0, value=int(default_expected), key="perform_expected")

    counted_str = st.text_input("Counted QTY", value=st.session_state.get("perform_counted_str",""), placeholder="Scan/enter count", key="perform_counted_str", on_change=_on_count_change)

    def _parse_count(s):
        s = (s or "").strip()
        if s == "": return None
        if not re.fullmatch(r"\d+", s): return "invalid"
        return int(s)

    counted_val = _parse_count(counted_str)
    note = st.text_input("Note (optional)", key="perform_note")

    if auto_focus and not st.session_state.get("_did_autofocus"):
        focus_by_label("Scan Location"); st.session_state["_did_autofocus"] = True
    target = st.session_state.get("_focus_target_label","")
    if auto_advance and target:
        focus_by_label(target); st.session_state["_focus_target_label"] = ""

    if assignment_id and assignee and st.button("Start / Renew 20-min Lock", use_container_width=True, key="perform_lock_btn"):
        try:
            ok, msg = start_or_renew_lock(assignment_id, assignee)
            st.success(msg) if ok else st.warning(msg)
            if ok: queue_feedback("success")
        except Exception as e:
            st.warning(f"Lock error: {e}"); queue_feedback("error")

    if st.button("Submit Count", type="primary", key="perform_submit_btn", use_container_width=True):
        if not assignee or not location:
            st.warning("Assignee and Location are required."); queue_feedback("error")
        elif counted_val in (None, "invalid"):
            st.warning("Enter a valid non-negative integer for Counted QTY."); queue_feedback("error")
        else:
            ok, why = validate_lock_for_submit(assignment_id, assignee)
            if not ok:
                st.error(why); queue_feedback("error")
            else:
                variance = counted_val - expected_num if expected_num is not None else ""
                flag = "Match" if variance=="" or variance==0 else ("Over" if variance>0 else "Short")
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
                    "variance_flag": flag,
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
                st.success("Submitted"); queue_feedback("success")
                st.session_state["perform_counted_str"] = ""

    if auto_submit and st.session_state.get("_auto_submit_try", False):
        st.session_state["_auto_submit_try"] = False
        if assignee and location and (counted_val not in (None, "invalid")):
            ok, why = validate_lock_for_submit(assignment_id, assignee)
            if ok:
                variance = counted_val - expected_num if expected_num is not None else ""
                flag = "Match" if variance=="" or variance==0 else ("Over" if variance>0 else "Short")
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
                    "variance_flag": flag,
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
                st.success("Submitted (auto)"); queue_feedback("success")
                st.session_state["perform_counted_str"] = ""
            else:
                st.error(why); queue_feedback("error")
    emit_feedback()

# ---------- Dashboard (Live)
with tabs[3]:
    st.subheader("Dashboard (Live)")
    subs_path = PATHS["subs"]
    refresh_sec = st.slider("Auto-refresh every (seconds)", 2, 30, 5, key="dash_refresh")
    st.caption(f"Submissions file: {subs_path}")
    dfS = load_submissions()
    dfS_disp = dfS.copy()
    if st.session_state.get("mobile_mode", True) and not dfS_disp.empty:
        keep = [c for c in ["timestamp","assignee","location","counted_qty","expected_qty","variance","variance_flag"] if c in dfS_disp.columns]
        if keep: dfS_disp = dfS_disp[keep]
    today_str = datetime.now().strftime("%m/%d/%Y")
    today_df = dfS[dfS["timestamp"].str.contains(today_str)] if not dfS.empty else dfS
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Counts Today", int(len(today_df)))
    c2.metric("Over", int((today_df["variance_flag"]=="Over").sum()) if not today_df.empty else 0)
    c3.metric("Short", int((today_df["variance_flag"]=="Short").sum()) if not today_df.empty else 0)
    c4.metric("Match", int((today_df["variance_flag"]=="Match").sum()) if not today_df.empty else 0)
    st.write("Latest Submissions")
    show_table(dfS_disp, height=320, key="grid_submissions", numeric_cols=["variance"])
    last_mod = os.path.getmtime(subs_path) if os.path.exists(subs_path) else 0
    time.sleep(refresh_sec)
    if os.path.exists(subs_path) and os.path.getmtime(subs_path) != last_mod:
        st.rerun()

# ---------- Discrepancies
with tabs[4]:
    st.subheader("Discrepancies")
    dfS = load_submissions()
    ex = dfS[dfS["variance_flag"].isin(["Over","Short"])]
    ex_disp = ex.copy()
    if st.session_state.get("mobile_mode", True) and not ex_disp.empty:
        keep = [c for c in ["timestamp","assignee","location","counted_qty","expected_qty","variance","variance_flag","note"] if c in ex_disp.columns]
        if keep: ex_disp = ex_disp[keep]
    st.write("Exceptions")
    show_table(ex_disp, height=300, key="grid_exceptions", numeric_cols=["variance"])
    st.download_button("Export Exceptions CSV", data=ex.to_csv(index=False), file_name="cyclecount_exceptions.csv", mime="text/csv", key="disc_export_btn")

# ---------- Settings (mapping defaults: saved -> session -> DEFAULT_MAPPING)
with tabs[5]:
    st.subheader("Settings")
    st.write("Environment variables (optional):")
    st.code("""CYCLE_COUNT_LOG_DIR=<shared path>
BIN_HELPER_LOG_DIR=<fallback if set>
CC_LOCK_MINUTES=<default 20>
AGGRID_ENABLED=<1 or 0>""", language="bash")
    st.caption("Tip: point CYCLE_COUNT_LOG_DIR to your OneDrive JT Logistics folder so counters and your dashboard use the same files.")
    st.write("Active paths:", PATHS)
    st.divider()
    st.markdown("### Inventory Excel — Upload & Map")
    inv_df_cached = load_cached_inventory()
    if not inv_df_cached.empty:
        st.success(f"Inventory cache loaded: {len(inv_df_cached):,} rows")
        st.dataframe(inv_df_cached.head(10), use_container_width=True)

    upload = st.file_uploader("Upload Inventory Excel (.xlsx/.xls/.csv)", type=["xlsx","xls","csv"], key="settings_upload_inv")
    if upload is not None:
        try:
            name = getattr(upload, "name", "") or ""
            ext = (name.lower().split(".")[-1] if "." in name else "")
            if ext == "csv":
                raw = read_csv_fallback(upload, dtype=str).fillna("")
                st.write("Preview (first 10 rows):"); st.dataframe(raw.head(10), use_container_width=True)
            else:
                engine = "openpyxl" if ext == "xlsx" else "xlrd"
                xls = pd.ExcelFile(upload, engine=engine)
                sheet = st.selectbox("Select sheet", xls.sheet_names, index=0, key="settings_sheet")
                raw = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
                st.write("Preview (first 10 rows):"); st.dataframe(raw.head(10), use_container_width=True)

            # Priority: saved mapping -> session mapping -> DEFAULT_MAPPING
            mapping_saved = load_inventory_mapping() or {}
            mapping_session = _get_session_mapping()
            base_map = {**DEFAULT_MAPPING, **mapping_session, **mapping_saved}

            cols = list(raw.columns)
            st.markdown("#### Column Mapping")

            def idx_for(colname):
                return (cols.index(colname)+1) if (colname in cols and colname) else 0

            c1,c2,c3,c4,c5 = st.columns(5)
            with c1: loc_col = st.selectbox("Location", ["<none>"]+cols, index=idx_for(base_map.get("location","")), key="map_loc")
            with c2: sku_col = st.selectbox("SKU", ["<none>"]+cols, index=idx_for(base_map.get("sku","")), key="map_sku")
            with c3: lot_col = st.selectbox("LOT Number", ["<none>"]+cols, index=idx_for(base_map.get("lot_number","")), key="map_lot")
            with c4: pal_col = st.selectbox("Pallet ID", ["<none>"]+cols, index=idx_for(base_map.get("pallet_id","")), key="map_pal")
            with c5: qty_col = st.selectbox("Expected QTY", ["<none>"]+cols, index=idx_for(base_map.get("expected_qty","")), key="map_qty")

            current_map = {
                "location": (st.session_state.get("map_loc") if st.session_state.get("map_loc") and st.session_state.get("map_loc")!="<none>" else ""),
                "sku": (st.session_state.get("map_sku") if st.session_state.get("map_sku") and st.session_state.get("map_sku")!="<none>" else ""),
                "lot_number": (st.session_state.get("map_lot") if st.session_state.get("map_lot") and st.session_state.get("map_lot")!="<none>" else ""),
                "pallet_id": (st.session_state.get("map_pal") if st.session_state.get("map_pal") and st.session_state.get("map_pal")!="<none>" else ""),
                "expected_qty": (st.session_state.get("map_qty") if st.session_state.get("map_qty") and st.session_state.get("map_qty")!="<none>" else ""),
            }
            _set_session_mapping(current_map)

            if st.button("Save Mapping & Cache Inventory", type="primary", key="map_save_btn"):
                norm = normalize_inventory_df(raw, current_map)
                save_inventory_cache(norm); save_inventory_mapping(current_map)
                st.success(f"Saved mapping and cached {len(norm):,} rows."); st.rerun()
        except Exception as e:
            st.warning(f"Excel load/mapping error: {e}")
