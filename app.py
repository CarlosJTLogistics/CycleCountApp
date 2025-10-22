import os, time, uuid, re, json
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st

# Try to import AgGrid; fall back gracefully if not available
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    _AGGRID_IMPORTED = True
except Exception:
    _AGGRID_IMPORTED = False

# ========= App meta =========
APP_NAME = "Cycle Counting"
VERSION = "v1.1.1 (stable keys + xls/csv + safe grid)"
TZ_LABEL = "US/Central"
LOCK_MINUTES_DEFAULT = 20
LOCK_MINUTES = int(os.getenv("CC_LOCK_MINUTES", LOCK_MINUTES_DEFAULT))

# ========= Core utils =========
TS_FMT = "%m/%d/%Y %I:%M:%S %p"

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
            return pd.read_csv(path, dtype=str).fillna("")
        except Exception:
            time.sleep(0.1)
    return pd.DataFrame(columns=columns or [])

def now_str(): return datetime.now().strftime(TS_FMT)
def mk_id(prefix): return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
def parse_ts(s: str):
    try: return datetime.strptime(s, TS_FMT)
    except Exception: return None

# ========= Data access =========
def load_assignments():
    df = read_csv_locked(PATHS["assign"], ASSIGN_COLS)
    for c in ["lock_owner","lock_start_ts","lock_expires_ts"]:
        if c not in df.columns: df[c] = ""
    return df

def save_assignments(df: pd.DataFrame):
    for c in ASSIGN_COLS:
        if c not in df.columns: df[c] = ""
    df[ASSIGN_COLS].to_csv(PATHS["assign"], index=False, encoding="utf-8")

def load_submissions(): return read_csv_locked(PATHS["subs"], SUBMIT_COLS)

# ========= Inventory Excel/CSV support =========
def load_cached_inventory() -> pd.DataFrame:
    if "inv_df" in st.session_state:
        return st.session_state["inv_df"]
    if os.path.exists(PATHS["inv_csv"]):
        try:
            inv = pd.read_csv(PATHS["inv_csv"], dtype=str).fillna("")
            st.session_state["inv_df"] = inv
            return inv
        except Exception:
            pass
    return pd.DataFrame(columns=["location","sku","lot_number","pallet_id","expected_qty"])

def save_inventory_cache(df: pd.DataFrame):
    df.to_csv(PATHS["inv_csv"], index=False, encoding="utf-8")
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
    out["location"] = df[mapping.get("location","")].astype(str) if mapping.get("location","") in df.columns else ""
    out["sku"] = df[mapping.get("sku","")].astype(str) if mapping.get("sku","") in df.columns else ""
    lot_col = mapping.get("lot_number","")
    out["lot_number"] = df[lot_col].astype(str).map(lot_normalize) if lot_col in df.columns else ""
    out["pallet_id"] = df[mapping.get("pallet_id","")].astype(str) if mapping.get("pallet_id","") in df.columns else ""
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

# ========= Lock helpers =========
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

# ========= AgGrid safe wrapper =========
AGGRID_ENABLED = (os.getenv("AGGRID_ENABLED","1") == "1") and _AGGRID_IMPORTED

def show_table(df, height=300, key=None, selectable=False, selection_mode="single", numeric_cols=None):
    if df is None or (hasattr(df, "empty") and df.empty):
        st.info("No data")
        return {"selected_rows": []}
    if AGGRID_ENABLED:
        try:
            gob = GridOptionsBuilder.from_dataframe(df)
            gob.configure_default_column(resizable=True, filter=True, sortable=True)
            if selectable:
                gob.configure_selection(selection_mode)
            if numeric_cols:
                for col in numeric_cols:
                    if col in df.columns:
                        gob.configure_column(col, type=["numericColumn"])
            return AgGrid(df, gridOptions=gob.build(),
                          update_mode=(GridUpdateMode.SELECTION_CHANGED if selectable else GridUpdateMode.NO_UPDATE),
                          height=height, key=key)
        except Exception as e:
            st.warning(f"AgGrid unavailable, falling back to simple table: {e}")
    st.dataframe(df, use_container_width=True, height=height)
    return {"selected_rows": []}

# ========= App UI =========
st.set_page_config(page_title=f"{APP_NAME} {VERSION}", layout="wide")
st.title(f"{APP_NAME} ({VERSION})")
st.caption(f"Active log dir: {PATHS['root']} · Timezone: {TZ_LABEL} · Lock: {LOCK_MINUTES} min")

tabs = st.tabs(["Assign Counts","My Assignments","Perform Count","Dashboard (Live)","Discrepancies","Settings"])

# ---------- Assign Counts ----------
with tabs[0]:
    st.subheader("Assign Counts")
    # --- Who's assigning / who gets it ---
    c_top1, c_top2 = st.columns(2)
    with c_top1:
        assigned_by = st.text_input("Assigned by", value=st.session_state.get("assigned_by",""), key="assign_assigned_by")
    with c_top2:
        assignee = st.text_input("Assign to (name)", value=st.session_state.get("assignee",""), key="assign_assignee")

    # --- Location chooser (multi-select) + paste list ---
    inv_df = load_cached_inventory()
    loc_options = []
    if inv_df is not None and hasattr(inv_df, "empty") and not inv_df.empty and "location" in inv_df.columns:
        loc_options = sorted(inv_df["location"].astype(str).str.strip().replace("nan","").dropna().unique().tolist())

    st.caption("Select one or more locations from the list, or paste a list (one per line). Other fields will auto-populate from your inventory cache.")
    colL, colR = st.columns([1.2, 1])

    with colL:
        selected_locs = st.multiselect(
            "Locations",
            options=loc_options,
            default=[],
            help="Search by typing; select multiple.",
            key="assign_locations_multiselect"
        )
        pasted = st.text_area(
            "Paste locations (optional)",
            value="",
            height=120,
            key="assign_locations_paste",
            placeholder="e.g.\n11400804\n11400805\nTUN01001"
        )
        # Merge selections + pasted (dedupe, keep selection order first)
        pasted_list = [ln.strip() for ln in pasted.splitlines() if ln.strip()] if pasted else []
        # Preserve order: selected first, then pasted uniques not already picked
        seen = set()
        loc_merge = []
        for s in selected_locs + pasted_list:
            if s not in seen:
                loc_merge.append(s); seen.add(s)

        notes = st.text_area(
            "Notes (optional)",
            value="",
            height=80,
            key="assign_notes",
            placeholder="Any special instructions for the counter..."
        )

        # Create one assignment per location (auto-fill details from inventory if present)
        disabled = (not assigned_by) or (not assignee) or (len(loc_merge) == 0)
        if st.button("Create Assignments", type="primary", disabled=disabled, key="assign_create_btn"):
            if not assigned_by or not assignee:
                st.warning("Assigned by and Assignee are required.")
            elif len(loc_merge) == 0:
                st.warning("Pick at least one location.")
            else:
                created = 0
                for loc in loc_merge:
                    sku = lot_num = pallet = expected = ""
                    if inv_df is not None and hasattr(inv_df, "empty") and not inv_df.empty:
                        cand = inv_df[inv_df["location"].astype(str).str.strip().str.lower() == str(loc).strip().lower()]
                        if not cand.empty:
                            # Use the first matching row
                            r = cand.iloc[0]
                            sku = str(r.get("sku","")).strip()
                            lot_num = lot_normalize(r.get("lot_number",""))
                            pallet = str(r.get("pallet_id","")).strip()
                            expected_val = r.get("expected_qty","")
                            try:
                                expected = str(int(float(expected_val))) if str(expected_val) != "" else ""
                            except Exception:
                                expected = str(expected_val) if str(expected_val) != "" else ""

                    row = {
                        "assignment_id": mk_id("CC"),
                        "assigned_by": assigned_by.strip(),
                        "assignee": assignee.strip(),
                        "location": str(loc).strip(),
                        "sku": sku,
                        "lot_number": lot_num,
                        "pallet_id": pallet,
                        "expected_qty": expected,
                        "priority": "Normal",         # keep column; default value
                        "status": "Assigned",
                        "created_ts": now_str(),
                        "due_date": "",               # removed from UI; leave blank in file
                        "notes": notes.strip(),
                        "lock_owner": "",
                        "lock_start_ts": "",
                        "lock_expires_ts": ""
                    }
                    safe_append_csv(PATHS["assign"], row, ASSIGN_COLS)
                    created += 1

                # remember names for convenience
                st.session_state["assigned_by"] = assigned_by
                st.session_state["assignee"] = assignee
                st.success(f"Created {created} assignment(s) for {assignee}.")

    # --- Existing assignment table remains ---
    st.divider()
    dfA = load_assignments()
    if not dfA.empty:
        def _lock_info(r):
            if lock_active(r):
                who = r.get("lock_owner","?")
                until = r.get("lock_expires_ts","")
                return f"🔒 {who} until {until}"
            return "Available"
        dfA_disp = dfA.copy()
        dfA_disp["lock_info"] = dfA_disp.apply(_lock_info, axis=1)
        st.write("All Assignments")
        show_table(dfA_disp, height=300, key="grid_all_assign")
    else:
        st.info("No assignments yet.")
with tabs[1]:
    st.subheader("My Assignments")
    me = st.text_input("I am (name)", key="me_name", value=st.session_state.get("assignee",""))
    dfA = load_assignments()
    mine = dfA[dfA["assignee"].str.lower()==(me or "").lower()] if me else dfA.iloc[0:0]

    cA, cB, cC, cD = st.columns(4)
    cA.metric("Open", int((mine["status"]=="Assigned").sum()))
    cB.metric("In Progress", int((mine["status"]=="In Progress").sum()))
    cC.metric("Submitted", int((mine["status"]=="Submitted").sum()))
    cD.metric("Total", int(len(mine)))

    st.write("Your Assignments")
    if not mine.empty:
        def _lock_info2(r):
            if lock_active(r):
                who = r.get("lock_owner","?")
                until = r.get("lock_expires_ts","")
                if lock_owned_by(r, me): return f"🔒 You until {until}"
                return f"🔒 {who} until {until}"
            return "Available"
        mine_disp = mine.copy()
        mine_disp["lock_info"] = mine_disp.apply(_lock_info2, axis=1)
        res = show_table(mine_disp, height=280, key="grid_my_assign", selectable=True, selection_mode="single")
        sel = res.get("selected_rows", [])
        if sel:
            selected = sel[0]
            st.session_state["current_assignment"] = selected
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Start / Renew 20-min Lock", type="primary", use_container_width=True, key="my_lock_btn"):
                    ok, msg = start_or_renew_lock(selected["assignment_id"], me)
                    if ok:
                        st.success(msg); st.rerun()
    # Removed Start/Renew Lock button for clarity
    st.info(selected.get("lock_info",""))  # Keep info only
                    else:
                        st.warning(msg)
            with c2:
                st.info(selected.get("lock_info",""))
    else:
        st.info("No assignments found for you.")

# ---------- Perform Count ----------
with tabs[2]:
    st.subheader("Perform Count")
    cur = st.session_state.get("current_assignment", {})
    assignment_id = st.text_input("Assignment ID", value=cur.get("assignment_id",""), key="perform_assignment_id")
    assignee = st.text_input("Assignee", value=cur.get("assignee", st.session_state.get("me_name","")), key="perform_assignee")
    c1,c2 = st.columns(2)
    with c1:
        location = st.text_input("Scan Location", value=cur.get("location",""), placeholder="Scan now", key="perform_location")
    with c2:
        pallet = st.text_input("Scan Pallet ID (optional)", value=cur.get("pallet_id",""), key="perform_pallet")
    c3,c4,c5 = st.columns(3)
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
    counted = st.number_input("Counted QTY", min_value=0, step=1, key="perform_counted")
    device_id = st.text_input("Device ID (optional)", value=os.getenv("DEVICE_ID",""), key="perform_device_id")
    note = st.text_input("Note (optional)", key="perform_note")
if assignment_id and assignee and st.button("Start / Renew 20-min Lock", use_container_width=True, key="perform_lock_btn"):
    try:
        ok, msg = start_or_renew_lock(assignment_id, assignee)
        st.success(msg) if ok else st.warning(msg)
    except Exception as e:
        st.warning(f"Lock error: {e}")
    if st.button("Submit Count", type="primary", key="perform_submit_btn"):
        if not assignee or not location:
            st.warning("Assignee and Location are required.")
        else:
            ok, why = validate_lock_for_submit(assignment_id, assignee)
            if not ok:
                st.error(why)
            else:
                variance = counted - expected_num if expected_num is not None else ""
                flag = "Match" if variance=="" or variance==0 else ("Over" if variance>0 else "Short")
                row = {
                    "submission_id": mk_id("CCS"),
                    "assignment_id": assignment_id or "",
                    "assignee": assignee.strip(),
                    "location": location.strip(),
                    "sku": sku.strip(),
                    "lot_number": lot_normalize(lot),
                    "pallet_id": pallet.strip(),
                    "counted_qty": int(counted),
                    "expected_qty": int(expected_num) if expected_num is not None else "",
                    "variance": variance if variance!="" else "",
                    "variance_flag": flag,
                    "timestamp": now_str(),
                    "device_id": device_id or "",
                    "note": note.strip(),
                }
                safe_append_csv(PATHS["subs"], row, SUBMIT_COLS)
                dfA = load_assignments()
                if assignment_id and not dfA.empty:
                    ix = dfA.index[dfA["assignment_id"]==assignment_id]
                    if len(ix)>0:
                        dfA.loc[ix, "status"] = "Submitted"
                        dfA.loc[ix, ["lock_owner","lock_start_ts","lock_expires_ts"]] = ["","",""]
                        save_assignments(dfA)
                st.success("Submitted")

# ---------- Dashboard (Live) ----------
with tabs[3]:
    st.subheader("Dashboard (Live)")
    subs_path = PATHS["subs"]
    refresh_sec = st.slider("Auto-refresh every (seconds)", 2, 30, 5, key="dash_refresh")
    st.caption(f"Submissions file: {subs_path}")
    dfS = load_submissions()
    today_str = datetime.now().strftime("%m/%d/%Y")
    today_df = dfS[dfS["timestamp"].str.contains(today_str)] if not dfS.empty else dfS
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Counts Today", int(len(today_df)))
    c2.metric("Over", int((today_df["variance_flag"]=="Over").sum()) if not today_df.empty else 0)
    c3.metric("Short", int((today_df["variance_flag"]=="Short").sum()) if not today_df.empty else 0)
    c4.metric("Match", int((today_df["variance_flag"]=="Match").sum()) if not today_df.empty else 0)
    st.write("Latest Submissions")
    show_table(dfS, height=320, key="grid_submissions", numeric_cols=["variance"])
    last_mod = os.path.getmtime(subs_path) if os.path.exists(subs_path) else 0
    time.sleep(refresh_sec)
    if os.path.exists(subs_path) and os.path.getmtime(subs_path) != last_mod:
        st.rerun()

# ---------- Discrepancies ----------
with tabs[4]:
    st.subheader("Discrepancies")
    dfS = load_submissions()
    ex = dfS[dfS["variance_flag"].isin(["Over","Short"])]
    st.write("Exceptions")
    show_table(ex, height=300, key="grid_exceptions", numeric_cols=["variance"])
    st.download_button("Export Exceptions CSV", data=ex.to_csv(index=False), file_name="cyclecount_exceptions.csv", mime="text/csv", key="disc_export_btn")

# ---------- Settings ----------
with tabs[5]:
    st.subheader("Settings")
    st.write("Environment variables (optional):")
    st.code("CYCLE_COUNT_LOG_DIR=<shared path>\nBIN_HELPER_LOG_DIR=<fallback if set>\nCC_LOCK_MINUTES=<default 20>\nAGGRID_ENABLED=<1 or 0>", language="bash")
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
                raw = pd.read_csv(upload, dtype=str).fillna("")
                st.write("Preview (first 10 rows):")
                st.dataframe(raw.head(10), use_container_width=True)
            else:
                engine = "openpyxl" if ext == "xlsx" else "xlrd"
                xls = pd.ExcelFile(upload, engine=engine)
                sheet = st.selectbox("Select sheet", xls.sheet_names, index=0, key="settings_sheet")
                raw = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
                st.write("Preview (first 10 rows):")
                st.dataframe(raw.head(10), use_container_width=True)
            cols = list(raw.columns)
            st.markdown("#### Column Mapping")
            mapping_prev = load_inventory_mapping()
            c1,c2,c3,c4,c5 = st.columns(5)
            with c1:
                loc_col = st.selectbox("Location", ["<none>"]+cols, index=(cols.index(mapping_prev.get("location",""))+1 if mapping_prev.get("location","") in cols else 0), key="map_loc")
            with c2:
                sku_col = st.selectbox("SKU", ["<none>"]+cols, index=(cols.index(mapping_prev.get("sku",""))+1 if mapping_prev.get("sku","") in cols else 0), key="map_sku")
            with c3:
                lot_col = st.selectbox("LOT Number", ["<none>"]+cols, index=(cols.index(mapping_prev.get("lot_number",""))+1 if mapping_prev.get("lot_number","") in cols else 0), key="map_lot")
            with c4:
                pal_col = st.selectbox("Pallet ID", ["<none>"]+cols, index=(cols.index(mapping_prev.get("pallet_id",""))+1 if mapping_prev.get("pallet_id","") in cols else 0), key="map_pal")
            with c5:
                qty_col = st.selectbox("Expected QTY", ["<none>"]+cols, index=(cols.index(mapping_prev.get("expected_qty",""))+1 if mapping_prev.get("expected_qty","") in cols else 0), key="map_qty")
            if st.button("Save Mapping & Cache Inventory", type="primary", key="map_save_btn"):
                mapping = {
                    "location": (loc_col if loc_col!="<none>" else ""),
                    "sku": (sku_col if sku_col!="<none>" else ""),
                    "lot_number": (lot_col if lot_col!="<none>" else ""),
                    "pallet_id": (pal_col if pal_col!="<none>" else ""),
                    "expected_qty": (qty_col if qty_col!="<none>" else ""),
                }
                norm = normalize_inventory_df(raw, mapping)
                save_inventory_cache(norm)
                save_inventory_mapping(mapping)
                st.success(f"Saved mapping and cached {len(norm):,} rows.")
                st.rerun()
        except Exception as e:
            st.warning(f"Excel load error: {e}")