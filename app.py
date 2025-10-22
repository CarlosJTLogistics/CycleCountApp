import os, time, uuid, re, json
from datetime import datetime, date, timedelta
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# ========= App meta =========
APP_NAME = "Cycle Counting"
VERSION = "v1.1.0 (Excel + 20min lock)"
TZ_LABEL = "US/Central"  # display-only label
LOCK_MINUTES_DEFAULT = 20
LOCK_MINUTES = int(os.getenv("CC_LOCK_MINUTES", LOCK_MINUTES_DEFAULT))

# ========= Core utils =========
TS_FMT = "%m/%d/%Y %I:%M:%S %p"

def lot_normalize(x:str)->str:
    if x is None or (isinstance(x,float) and pd.isna(x)): return ""
    s = re.sub(r"\D","", str(x))
    s = re.sub(r"^0+","", s)
    return s or ""

def ensure_dirs(paths):
    for p in paths: os.makedirs(p, exist_ok=True)

def get_paths():
    # Order: explicit env var -> Bin Helper fallback -> local ./logs
    base = os.getenv("CYCLE_COUNT_LOG_DIR") or os.getenv("BIN_HELPER_LOG_DIR") or os.path.join(os.getcwd(), "logs")
    # Streamlit Cloud mount (if present)
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

def safe_append_csv(path, row:dict, columns:list):
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

def parse_ts(s:str):
    try:
        return datetime.strptime(s, TS_FMT)
    except Exception:
        return None

# ========= Data access =========
def load_assignments():
    df = read_csv_locked(PATHS["assign"], ASSIGN_COLS)
    # Ensure lock columns exist
    for c in ["lock_owner","lock_start_ts","lock_expires_ts"]:
        if c not in df.columns: df[c] = ""
    return df

def save_assignments(df: pd.DataFrame):
    # Keep only defined columns (preserve order)
    for c in ASSIGN_COLS:
        if c not in df.columns: df[c] = ""
    df[ASSIGN_COLS].to_csv(PATHS["assign"], index=False, encoding="utf-8")

def load_submissions(): return read_csv_locked(PATHS["subs"], SUBMIT_COLS)

# ========= Inventory Excel support =========
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
    # Map selected columns into canonical names; missing -> blank
    out = pd.DataFrame()
    out["location"]   = df[mapping.get("location","")].astype(str) if mapping.get("location") in df.columns else ""
    out["sku"]        = df[mapping.get("sku","")].astype(str) if mapping.get("sku") in df.columns else ""
    lot_col = mapping.get("lot_number","")
    out["lot_number"] = df[lot_col].astype(str).map(lot_normalize) if lot_col in df.columns else ""
    out["pallet_id"]  = df[mapping.get("pallet_id","")].astype(str) if mapping.get("pallet_id") in df.columns else ""
    qty_col = mapping.get("expected_qty","")
    if qty_col in df.columns:
        # Force numeric, fill non-numeric as blank
        q = pd.to_numeric(df[qty_col], errors="coerce").fillna("").astype(str)
        out["expected_qty"] = q
    else:
        out["expected_qty"] = ""
    # Trim whitespace
    for c in ["location","sku","pallet_id"]:
        out[c] = out[c].str.strip()
    return out.fillna("")

def inv_lookup_expected(location:str, sku:str="", lot:str="", pallet_id:str=""):
    inv = load_cached_inventory()
    if inv.empty or not isinstance(inv, pd.DataFrame) or "expected_qty" not in inv.columns:
        return None
    # Prepare normalized keys
    loc = (location or "").strip()
    sku = (sku or "").strip()
    pal = (pallet_id or "").strip()
    lotN = lot_normalize(lot)
    if loc == "" and pal == "" and sku == "" and lotN == "":
        return None
    # Priority filters: more specific to less
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
            # Take the first numeric expected_qty
            for val in tmp["expected_qty"].tolist():
                try:
                    n = int(float(val))
                    return n
                except Exception:
                    continue
    return None

# ========= Lock helpers =========
def lock_active(row: pd.Series) -> bool:
    exp = parse_ts(row.get("lock_expires_ts",""))
    return bool(exp and exp > datetime.now())

def lock_owned_by(row: pd.Series, user:str) -> bool:
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

# ========= App UI =========
st.set_page_config(page_title=f"{APP_NAME} {VERSION}", layout="wide")
st.title(f"{APP_NAME} ({VERSION})")
st.caption(f"Active log dir: {PATHS['root']} · Timezone: {TZ_LABEL} · Lock: {LOCK_MINUTES} min")

tabs = st.tabs(["Assign Counts","My Assignments","Perform Count","Dashboard (Live)","Discrepancies","Settings"])

# ------------- Assign Counts -------------
with tabs[0]:
    st.subheader("Assign Counts")
    c_top1, c_top2 = st.columns(2)
    with c_top1:
        assigned_by = st.text_input("Assigned by", value=st.session_state.get("assigned_by",""), key="assign_assigned_by")
    with c_top2:
        assignee = st.text_input("Assign to (name, key="assign_assigned_by")", value=st.session_state.get("assignee",""))

    c1,c2,c3 = st.columns(3)
    with c1: location = st.text_input("Location (scan or type)", key="assign_location")
    with c2: sku = st.text_input("SKU (optional, key="assign_location")")
    with c3: lot = st.text_input("LOT Number (optional)", value="", help="Digits only; will be normalized")

    c4,c5,c6 = st.columns(3, key="assign_lot")
    with c4: pallet = st.text_input("Pallet ID (optional)")
    with c5: expected = st.number_input("Expected QTY (optional, key="assign_pallet")", min_value=0, value=0)
    with c6: priority = st.selectbox("Priority", ["Normal","High","Low"], index=0)

    due_date = st.date_input("Due date", value=date.today())
    notes = st.text_area("Notes (optional)", height=80)

    if st.button("Create Assignment", type="primary"):
        if not assigned_by or not assignee or not location:
            st.warning("Assigned by, Assignee, and Location are required.")
        else:
            row = {
                "assignment_id": mk_id("CC"),
                "assigned_by": assigned_by.strip(),
                "assignee": assignee.strip(),
                "location": location.strip(),
                "sku": sku.strip(),
                "lot_number": lot_normalize(lot),
                "pallet_id": pallet.strip(),
                "expected_qty": str(expected or ""),
                "priority": priority,
                "status": "Assigned",
                "created_ts": now_str(),
                "due_date": due_date.strftime("%Y-%m-%d"),
                "notes": notes.strip(),
                "lock_owner": "",
                "lock_start_ts": "",
                "lock_expires_ts": "",
            }
            safe_append_csv(PATHS["assign"], row, ASSIGN_COLS)
            st.session_state["assigned_by"]=assigned_by; st.session_state["assignee"]=assignee
            st.success(f"Assignment created for {assignee} at {location}")

    st.divider()
    dfA = load_assignments()
    if not dfA.empty:
        # Add helpful display col
        def lock_info(r):
            if lock_active(r):
                who = r.get("lock_owner","?")
                until = r.get("lock_expires_ts","")
                return f"🔒 {who} until {until}"
            return "Available"
        dfA_disp = dfA.copy()
        dfA_disp["lock_info"] = dfA_disp.apply(lock_info, axis=1)
        st.write("All Assignments")
        gob = GridOptionsBuilder.from_dataframe(dfA_disp)
        gob.configure_default_column(resizable=True, filter=True, sortable=True)
        gob.configure_selection("single")
        AgGrid(dfA_disp, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=300)
    else:
        st.info("No assignments yet.")

# ------------- My Assignments -------------
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
        # Display lock info and allow Start/Renew
        def lock_info(r):
            if lock_active(r):
                who = r.get("lock_owner","?")
                until = r.get("lock_expires_ts","")
                if lock_owned_by(r, me): return f"🔒 You until {until}"
                return f"🔒 {who} until {until}"
            return "Available"
        mine_disp = mine.copy()
        mine_disp["lock_info"] = mine_disp.apply(lock_info, axis=1)
        gob = GridOptionsBuilder.from_dataframe(mine_disp)
        gob.configure_default_column(resizable=True, filter=True, sortable=True)
        gob.configure_column("location", pinned="left")
        grid = AgGrid(mine_disp, gridOptions=gob.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, height=280)
        sel = grid["selected_rows"]
        if sel:
            selected = sel[0]
            st.session_state["current_assignment"] = selected
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Start / Renew 20-min Lock", type="primary", use_container_width=True):
                    ok, msg = start_or_renew_lock(selected["assignment_id"], me)
                    if ok: st.success(msg); st.rerun()
                    else: st.warning(msg)
            with c2:
                st.info(selected.get("lock_info",""))
    else:
        st.info("No assignments found for you.")

# ------------- Perform Count -------------
with tabs[2]:
    st.subheader("Perform Count")
    cur = st.session_state.get("current_assignment", {})
    assignment_id = st.text_input("Assignment ID", value=cur.get("assignment_id",""))
    assignee = st.text_input("Assignee", value=cur.get("assignee", st.session_state.get("me_name","", key="perform_assignment_id")))
    c1,c2 = st.columns(2)
    with c1: location = st.text_input("Scan Location", value=cur.get("location",""), placeholder="Scan now")
    with c2: pallet = st.text_input("Scan Pallet ID (optional, key="perform_location")", value=cur.get("pallet_id",""))
    c3,c4,c5 = st.columns(3)
    with c3: sku = st.text_input("SKU (optional)", value=cur.get("sku","", key="assign_sku"))
    with c4: lot = st.text_input("LOT Number (optional)", value=cur.get("lot_number",""))
    # Autofill expected from Inventory cache if available, else from assignment
    auto_expected = inv_lookup_expected(location, sku, lot, pallet, key="perform_lot")
    cur_exp = cur.get("expected_qty","")
    try_cur_exp = int(cur_exp) if str(cur_exp).isdigit() else None
    default_expected = auto_expected if auto_expected is not None else (try_cur_exp if try_cur_exp is not None else 0)
    with c5: expected_num = st.number_input("Expected QTY (auto from Inventory if available)", min_value=0, value=int(default_expected))
    counted = st.number_input("Counted QTY", min_value=0, step=1)
    device_id = st.text_input("Device ID (optional)", value=os.getenv("DEVICE_ID",""))
    note = st.text_input("Note (optional, key="perform_device_id")")

    # Quick lock control
    if assignment_id and assignee and st.button("Start / Renew 20-min Lock", use_container_width=True):
        ok, msg = start_or_renew_lock(assignment_id, assignee)
        st.success(msg) if ok else st.warning(msg)

    if st.button("Submit Count", type="primary"):
        if not assignee or not location:
            st.warning("Assignee and Location are required.")
        else:
            # Validate lock
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

                # Mark assignment as Submitted (if known)
                dfA = load_assignments()
                if assignment_id and not dfA.empty:
                    ix = dfA.index[dfA["assignment_id"]==assignment_id]
                    if len(ix)>0:
                        dfA.loc[ix, "status"] = "Submitted"
                        # Clear lock on submit
                        dfA.loc[ix, ["lock_owner","lock_start_ts","lock_expires_ts"]] = ["","",""]
                        save_assignments(dfA)
                st.success("Submitted")

# ------------- Dashboard (Live) -------------
with tabs[3]:
    st.subheader("Dashboard (Live)")
    subs_path = PATHS["subs"]
    refresh_sec = st.slider("Auto-refresh every (seconds)", 2, 30, 5)
    st.caption(f"Submissions file: {subs_path}")
    dfS = load_submissions()

    # KPIs (Today)
    today_str = datetime.now().strftime("%m/%d/%Y")
    today_df = dfS[dfS["timestamp"].str.contains(today_str)] if not dfS.empty else dfS
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Counts Today", int(len(today_df)))
    c2.metric("Over", int((today_df["variance_flag"]=="Over").sum()))
    c3.metric("Short", int((today_df["variance_flag"]=="Short").sum()))
    c4.metric("Match", int((today_df["variance_flag"]=="Match").sum()))

    st.write("Latest Submissions")
    gob = GridOptionsBuilder.from_dataframe(dfS)
    gob.configure_default_column(resizable=True, filter=True, sortable=True)
    gob.configure_column("variance", type=["numericColumn"])
    AgGrid(dfS, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=320)

    # File-change-triggered refresh
    last_mod = os.path.getmtime(subs_path) if os.path.exists(subs_path) else 0
    time.sleep(refresh_sec)
    if os.path.exists(subs_path) and os.path.getmtime(subs_path) != last_mod:
        st.rerun()

# ------------- Discrepancies -------------
with tabs[4]:
    st.subheader("Discrepancies")
    dfS = load_submissions()
    ex = dfS[dfS["variance_flag"].isin(["Over","Short"])]
    st.write("Exceptions")
    gob = GridOptionsBuilder.from_dataframe(ex)
    gob.configure_default_column(resizable=True, filter=True, sortable=True)
    AgGrid(ex, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=300)
    st.download_button("Export Exceptions CSV", data=ex.to_csv(index=False), file_name="cyclecount_exceptions.csv", mime="text/csv")

# ------------- Settings -------------
with tabs[5]:
    st.subheader("Settings")
    st.write("Environment variables (optional):")
    st.code("CYCLE_COUNT_LOG_DIR=<shared path>\nBIN_HELPER_LOG_DIR=<fallback if set>\nCC_LOCK_MINUTES=<default 20>", language="bash")
    st.caption("Tip: point CYCLE_COUNT_LOG_DIR to your OneDrive JT Logistics folder so counters and your dashboard use the same files.")
    st.write("Active paths:", PATHS)
    st.divider()

    st.markdown("### Inventory Excel — Upload & Map")
    inv_df_cached = load_cached_inventory()
    if not inv_df_cached.empty:
        st.success(f"Inventory cache loaded: {len(inv_df_cached):,} rows")
        st.dataframe(inv_df_cached.head(10), use_container_width=True)
    upload = st.file_uploader("Upload Inventory Excel (.xlsx/.xls)", type=["xlsx","xls"])
    mapping_hint = "Map your columns to: location, sku, lot_number, pallet_id, expected_qty"
    if upload is not None:
        try:
            # Read first sheet by default; allow selecting a sheet
            xls = pd.ExcelFile(upload, engine="openpyxl")
            sheet = st.selectbox("Select sheet", xls.sheet_names, index=0)
            raw = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
            st.write("Preview (first 10 rows):")
            st.dataframe(raw.head(10), use_container_width=True)
            cols = list(raw.columns)
            st.markdown("#### Column Mapping")
            mapping_prev = load_inventory_mapping()
            c1,c2,c3,c4,c5 = st.columns(5)
            with c1: loc_col = st.selectbox("Location", ["<none>"]+cols, index=(cols.index(mapping_prev.get("location",""))+1 if mapping_prev.get("location","") in cols else 0))
            with c2: sku_col = st.selectbox("SKU", ["<none>"]+cols, index=(cols.index(mapping_prev.get("sku",""))+1 if mapping_prev.get("sku","") in cols else 0))
            with c3: lot_col = st.selectbox("LOT Number", ["<none>"]+cols, index=(cols.index(mapping_prev.get("lot_number",""))+1 if mapping_prev.get("lot_number","") in cols else 0))
            with c4: pal_col = st.selectbox("Pallet ID", ["<none>"]+cols, index=(cols.index(mapping_prev.get("pallet_id",""))+1 if mapping_prev.get("pallet_id","") in cols else 0))
            with c5: qty_col = st.selectbox("Expected QTY", ["<none>"]+cols, index=(cols.index(mapping_prev.get("expected_qty",""))+1 if mapping_prev.get("expected_qty","") in cols else 0))
            if st.button("Save Mapping & Cache Inventory", type="primary"):
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

