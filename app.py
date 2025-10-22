import os, time, uuid, re
from datetime import datetime, date
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

APP_NAME = "Cycle Counting"; VERSION = "v1.0.0"; TZ_LABEL = "US/Central"

def lot_normalize(x:str)->str:
    if x is None or (isinstance(x,float) and pd.isna(x)): return ""
    import re as _re
    s = _re.sub(r"\D","", str(x))
    s = _re.sub(r"^0+","", s)
    return s or ""

def ensure_dirs(paths):
    for p in paths: os.makedirs(p, exist_ok=True)

def get_paths():
    base = os.getenv("CYCLE_COUNT_LOG_DIR") or os.getenv("BIN_HELPER_LOG_DIR") or os.path.join(os.getcwd(), "logs")
    cloud = "/mount/src/bin-helper/logs"
    active = cloud if os.path.isdir(cloud) else base
    ensure_dirs([active])
    return {"root":active, "assign":os.path.join(active,"counts_assignments.csv"), "subs":os.path.join(active,"cyclecount_submissions.csv")}

PATHS = get_paths()

ASSIGN_COLS = ["assignment_id","assigned_by","assignee","location","sku","lot_number","pallet_id","expected_qty","priority","status","created_ts","due_date","notes"]
SUBMIT_COLS = ["submission_id","assignment_id","assignee","location","sku","lot_number","pallet_id","counted_qty","expected_qty","variance","variance_flag","timestamp","device_id","note"]

def safe_append_csv(path,row:dict,columns:list):
    exists = os.path.exists(path); df = pd.DataFrame([row], columns=columns); tmp = path + ".tmp"
    if exists:
        with open(tmp,"a",encoding="utf-8") as f: df.to_csv(f, header=False, index=False)
        with open(tmp,"rb") as fin, open(path,"ab") as fout: fout.write(fin.read())
        os.remove(tmp)
    else:
        df.to_csv(path, index=False, encoding="utf-8")

def read_csv_locked(path, columns=None):
    if not os.path.exists(path): return pd.DataFrame(columns=columns or [])
    for _ in range(5):
        try: return pd.read_csv(path, dtype=str).fillna("")
        except Exception: time.sleep(0.1)
    return pd.DataFrame(columns=columns or [])

def now_str(): return datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
def mk_id(prefix): import uuid as _uuid; return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_uuid.uuid4().hex[:6].upper()}"

def load_assignments(): return read_csv_locked(PATHS["assign"], ASSIGN_COLS)
def load_submissions(): return read_csv_locked(PATHS["subs"], SUBMIT_COLS)

st.set_page_config(page_title=f"{APP_NAME} {VERSION}", layout="wide")
st.title(f"{APP_NAME} ({VERSION})")
st.caption(f"Active log dir: {PATHS['root']} · Timezone: {TZ_LABEL}")

tabs = st.tabs(["Assign Counts","My Assignments","Perform Count","Dashboard (Live)","Discrepancies","Settings"])

with tabs[0]:
    st.subheader("Assign Counts")
    c_top1, c_top2 = st.columns(2)
    with c_top1: assigned_by = st.text_input("Assigned by", value=st.session_state.get("assigned_by",""))
    with c_top2: assignee = st.text_input("Assign to (name)", value=st.session_state.get("assignee",""))
    c1,c2,c3 = st.columns(3)
    with c1: location = st.text_input("Location (scan or type)")
    with c2: sku = st.text_input("SKU (optional)")
    with c3: lot = st.text_input("LOT Number (optional)", value="", help="Digits only; will be normalized")
    c4,c5,c6 = st.columns(3)
    with c4: pallet = st.text_input("Pallet ID (optional)")
    with c5: expected = st.number_input("Expected QTY (optional)", min_value=0, value=0)
    with c6: priority = st.selectbox("Priority", ["Normal","High","Low"], index=0)
    due_date = st.date_input("Due date", value=date.today())
    notes = st.text_area("Notes (optional)", height=80)
    if st.button("Create Assignment", type="primary"):
        if not assigned_by or not assignee or not location:
            st.warning("Assigned by, Assignee, and Location are required.")
        else:
            row = {"assignment_id":mk_id("CC"),"assigned_by":assigned_by.strip(),"assignee":assignee.strip(),"location":location.strip(),"sku":sku.strip(),"lot_number":lot_normalize(lot),"pallet_id":pallet.strip(),"expected_qty":str(expected or ""),"priority":priority,"status":"Assigned","created_ts":now_str(),"due_date":due_date.strftime("%Y-%m-%d"),"notes":notes.strip()}
            safe_append_csv(PATHS["assign"], row, ASSIGN_COLS)
            st.session_state["assigned_by"]=assigned_by; st.session_state["assignee"]=assignee
            st.success(f"Assignment created for {assignee} at {location}")
    st.divider()
    dfA = load_assignments()
    st.write("All Assignments")
    if not dfA.empty:
        gob = GridOptionsBuilder.from_dataframe(dfA); gob.configure_default_column(resizable=True, filter=True, sortable=True); gob.configure_selection("single")
        AgGrid(dfA, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=300)
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
        gob = GridOptionsBuilder.from_dataframe(mine); gob.configure_default_column(resizable=True, filter=True, sortable=True); gob.configure_column("location", pinned="left")
        grid = AgGrid(mine, gridOptions=gob.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, height=280)
        sel = grid["selected_rows"]
        if sel:
            st.session_state["current_assignment"] = sel[0]
            st.info(f"Selected {sel[0]['assignment_id']} at {sel[0]['location']}")
    else:
        st.info("No assignments found for you.")

with tabs[2]:
    st.subheader("Perform Count")
    cur = st.session_state.get("current_assignment", {})
    assignment_id = st.text_input("Assignment ID", value=cur.get("assignment_id",""))
    assignee = st.text_input("Assignee", value=cur.get("assignee", st.session_state.get("me_name","")))
    c1,c2 = st.columns(2)
    with c1: location = st.text_input("Scan Location", value=cur.get("location",""), placeholder="Scan now")
    with c2: pallet = st.text_input("Scan Pallet ID (optional)", value=cur.get("pallet_id",""))
    c3,c4,c5 = st.columns(3)
    with c3: sku = st.text_input("SKU (optional)", value=cur.get("sku",""))
    with c4: lot = st.text_input("LOT Number (optional)", value=cur.get("lot_number",""))
    with c5: expected = st.text_input("Expected QTY (optional)", value=cur.get("expected_qty",""))
    counted = st.number_input("Counted QTY", min_value=0, step=1)
    device_id = st.text_input("Device ID (optional)", value=os.getenv("DEVICE_ID",""))
    note = st.text_input("Note (optional)")
    if st.button("Submit Count", type="primary"):
        if not assignee or not location:
            st.warning("Assignee and Location are required.")
        else:
            expected_num = int(expected) if str(expected).isdigit() else None
            variance = (counted - expected_num) if expected_num is not None else ""
            flag = "Match" if variance=="" or variance==0 else ("Over" if variance>0 else "Short")
            row = {"submission_id":mk_id("CCS"),"assignment_id":assignment_id or "","assignee":assignee.strip(),"location":location.strip(),"sku":sku.strip(),"lot_number":lot_normalize(lot),"pallet_id":pallet.strip(),"counted_qty":int(counted),"expected_qty":expected_num if expected_num is not None else "","variance":variance if variance!="" else "","variance_flag":flag,"timestamp":now_str(),"device_id":device_id or "","note":note.strip()}
            safe_append_csv(PATHS["subs"], row, SUBMIT_COLS)
            dfA = load_assignments()
            if assignment_id and not dfA.empty:
                ix = dfA.index[dfA["assignment_id"]==assignment_id]
                if len(ix)>0:
                    dfA.loc[ix, "status"] = "Submitted"
                    dfA.to_csv(PATHS["assign"], index=False)
            st.success("Submitted")

with tabs[3]:
    st.subheader("Dashboard (Live)")
    subs_path = PATHS["subs"]
    refresh_sec = st.slider("Auto-refresh every (seconds)", 2, 30, 5)
    st.caption(f"Submissions file: {subs_path}")
    dfS = load_submissions()
    today_str = datetime.now().strftime("%m/%d/%Y")
    today_df = dfS[dfS["timestamp"].str.contains(today_str)] if not dfS.empty else dfS
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Counts Today", int(len(today_df)))
    c2.metric("Over", int((today_df["variance_flag"]=="Over").sum()))
    c3.metric("Short", int((today_df["variance_flag"]=="Short").sum()))
    c4.metric("Match", int((today_df["variance_flag"]=="Match").sum()))
    st.write("Latest Submissions")
    gob = GridOptionsBuilder.from_dataframe(dfS); gob.configure_default_column(resizable=True, filter=True, sortable=True); gob.configure_column("variance", type=["numericColumn"])
    AgGrid(dfS, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=320)
    last_mod = os.path.getmtime(subs_path) if os.path.exists(subs_path) else 0
    time.sleep(refresh_sec)
    if os.path.exists(subs_path) and os.path.getmtime(subs_path) != last_mod:
        st.rerun()

with tabs[4]:
    st.subheader("Discrepancies")
    dfS = load_submissions()
    ex = dfS[dfS["variance_flag"].isin(["Over","Short"])]
    st.write("Exceptions")
    gob = GridOptionsBuilder.from_dataframe(ex); gob.configure_default_column(resizable=True, filter=True, sortable=True)
    AgGrid(ex, gridOptions=gob.build(), update_mode=GridUpdateMode.NO_UPDATE, height=300)
    st.download_button("Export Exceptions CSV", data=ex.to_csv(index=False), file_name="cyclecount_exceptions.csv", mime="text/csv")

with tabs[5]:
    st.subheader("Settings")
    st.write("Environment variables (optional):")
    st.code("CYCLE_COUNT_LOG_DIR=<preferred shared path>\nBIN_HELPER_LOG_DIR=<fallback if already set>", language="bash")
    st.caption("Tip: point CYCLE_COUNT_LOG_DIR to your OneDrive JT Logistics folder so counters and your dashboard use the same files.")
    st.write("Active paths:", PATHS)
