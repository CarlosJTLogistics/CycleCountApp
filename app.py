# ===== CycleCountApp surgical repair: replace 'My Assignments' tab block; fix commas; fix LOT regex =====
param(
  [string]$Repo = 'C:\Users\carlos.pacheco.MYA-LOGISTICS\OneDrive - JT Logistics\CycleCountApp',
  [string]$File = 'app.py',
  [string]$MainBranch = 'main'
)

function Die([string]$msg) { Write-Error $msg; exit 1 }

# Basic checks
if (!(Test-Path $Repo)) { Die "Repo path not found: $Repo" }
$AppPath = Join-Path $Repo $File
if (!(Test-Path $AppPath)) { Die "Target file not found: $AppPath" }

git -C $Repo rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Die "Not a git repo: $Repo" }

# Backup branch & tag
git -C $Repo fetch --all --prune | Out-Null
git -C $Repo checkout $MainBranch | Out-Null
git -C $Repo pull --ff-only 2>$null | Out-Null

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$backupBranch = "backup/cyclecountapp-$ts"
$backupTag    = "prefix/cyclecountapp-$ts"
git -C $Repo branch $backupBranch | Out-Null
git -C $Repo tag -a $backupTag -m "Pre-fix snapshot $ts" | Out-Null

# Read file (strip BOM)
[string]$raw = [System.IO.File]::ReadAllText($AppPath)
if ($raw.Length -gt 0 -and $raw[0] -eq [char]0xFEFF) { $raw = $raw.Substring(1) }

# ---------- Build the corrected 'My Assignments' block ----------
$myAssignments = @"
with tabs[1]:
    st.subheader(t("my_title"))
    me = st.text_input(t("i_am"), key="me_name")

    dfA = load_assignments()
    mine = (dfA[(dfA["assignee"].str.lower() == (me or "").lower()) & (dfA["status"] != "Submitted")]) if me else dfA.iloc[0:0]

    cA, cB, cC, cD = st.columns(4)
    cA.metric(t("open"), int((mine["status"] == "Assigned").sum()))
    cB.metric(t("in_progress"), int((mine["status"] == "In Progress").sum()))
    cC.metric(t("submitted"), int((mine["status"] == "Submitted").sum()))
    cD.metric(t("total"), int(len(mine)))

    st.write(t("your_assign"))

    # ---- Batch (My Assignments only) ----
    batch_mode = st.checkbox(t("batch_mode"), key="my_batch_mode")
    if batch_mode and not mine.empty:
        opts2 = []
        for _, r in mine.iterrows():
            label = f"{r.get('assignment_id','')} — {r.get('location','')} — {r.get('status','')}"
            opts2.append((label, r.get("assignment_id","")))

        def _fmt2(val):
            for lbl, v in opts2:
                if v == val:
                    return lbl
            return val

        selected_ids = st.multiselect(t("your_assign"), [v for _, v in opts2], format_func=_fmt2, key="my_assign_multi_simple")
        st.caption(t("selected_n", n=len(selected_ids)))

        if st.button(t("start_selected"), type="primary", key="my_start_selected_btn", use_container_width=True, disabled=(len(selected_ids) == 0)):
            # Deduplicate while preserving order
            seen = set(); q = []
            for sid in selected_ids:
                if sid and sid not in seen:
                    seen.add(sid); q.append(sid)
            st.session_state["batch_queue"] = q

            next_id = st.session_state["batch_queue"].pop(0)
            dfA2 = load_assignments()
            row2 = dfA2[dfA2["assignment_id"] == next_id]
            if not row2.empty:
                r2 = row2.iloc[0]
                me_name = st.session_state.get("me_name","") or r2.get("assignee","")
                ok2, msg2 = start_or_renew_lock(next_id, me_name)
                if ok2:
                    st.session_state["current_assignment"] = r2.to_dict()
                    switch_to_tab(t("tab_perform")); queue_feedback("success"); st.rerun()

    # ---- Single-select (radio or AgGrid) ----
    selected_dict = None
    if not mine.empty:
        if AGGRID_ENABLED:
            def _lock_info2(r):
                if lock_active(r):
                    who = r.get("lock_owner","?"); until = r.get("lock_expires_ts","")
                    you = "You" if st.session_state.get("lang","en") == "en" else "Tú"
                    who_disp = you if (who or "").lower() == (me or "").lower() else who
                    return t("locked_by_until", who=who_disp, until=until)
                return t("available")

            mine_disp = mine.copy(); mine_disp["lock_info"] = mine_disp.apply(_lock_info2, axis=1)
            res = show_table(mine_disp, height=300, key="grid_my_assign", selectable=True, selection_mode="single")
            sel = res.get("selected_rows", [])
            if isinstance(sel, pd.DataFrame):
                srec = sel.to_dict(orient="records")
            elif isinstance(sel, list):
                srec = sel
            else:
                try:
                    srec = list(sel)
                except Exception:
                    srec = []
            if srec:
                selected_dict = srec[0]
        else:
            opts = []
            for _, r in mine.iterrows():
                label = f"{r.get('assignment_id','')} — {r.get('location','')} — {r.get('status','')}"
                opts.append((label, r.get("assignment_id","")))
            if opts:
                def _fmt(val):
                    for lbl, v in opts:
                        if v == val:
                            return lbl
                    return val
                choice = st.radio(t("radio_label"), [v for _, v in opts], format_func=_fmt, key="my_assign_choice")
                if choice:
                    selected_dict = mine[mine["assignment_id"] == choice].iloc[0].to_dict()
            else:
                st.info(t("no_assign"))
    else:
        st.info(t("no_assign"))

    if selected_dict:
        st.session_state["pending_assignment"] = selected_dict

    pending = st.session_state.get("pending_assignment")
    if pending:
        st.markdown(t("selected_summary", id=pending.get('assignment_id',''), loc=pending.get('location',''), status=pending.get('status','')))
        if st.button(t("submit_assignment"), type="primary", key="my_submit_assignment_btn", use_container_width=True):
            assign_id = pending.get("assignment_id","")
            if not me:
                st.error(t("err_enter_name")); queue_feedback("error")
            else:
                dfA2 = load_assignments()
                row = dfA2[dfA2["assignment_id"] == assign_id]
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
                            emit_feedback()
"@

# ---------- Replace exactly the 'with tabs[1]:' ... 'with tabs[2]:' block ----------
$patternTabs = "(?s)with\s+tabs\[1\]:.*?with\s+tabs\[2\]:"
if (-not [System.Text.RegularExpressions.Regex]::IsMatch($raw, $patternTabs)) {
  Die "Anchors not found (with tabs[1] .. with tabs[2]). Aborting to avoid wrong edits."
}

# Ensure the replacement ends with the start of tabs[2] label
# We'll re-add the 'with tabs[2]:' line explicitly after the replacement.
$prefix = [System.Text.RegularExpressions.Regex]::Split($raw, $patternTabs, 2)[0]
$suffixMatch = [System.Text.RegularExpressions.Regex]::Match($raw, "with\s+tabs\[2\]:.*", [System.Text.RegularExpressions.RegexOptions]::Singleline)
if (-not $suffixMatch.Success) { Die "Suffix (with tabs[2]:) not found. Aborting." }
$suffix = $suffixMatch.Value

# Fixes outside of the replaced block:
#  - AgGrid double commas
#  - LOT regex
$rawGlobal = $raw -replace ",\s*,\s*numeric_cols", ", numeric_cols"
$rawGlobal = $rawGlobal -replace 'r"(\^0)\\\+"', 'r"$1+"'  # r"^0\+" -> r"^0+"
$rawGlobal = $rawGlobal -replace "r'(\^0)\\\+'", "r'$1+'"

# Reconstruct file: prefix + My Assignments + '\nwith tabs[2]:' line starts suffix
$rebuilt = $prefix + "`r`n" + $myAssignments + "`r`n" + "with tabs[2]:" + ($suffix.Substring("with tabs[2]:".Length))

# Write back
[System.IO.File]::WriteAllText($AppPath, $rebuilt, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Replaced 'My Assignments' block and applied global minor fixes."

# ---------- Python syntax check ----------
$tmpPy = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "pycompile-$ts.py")
$pyCode = @"
import py_compile, sys
path = r'$AppPath'
try:
    py_compile.compile(path, doraise=True)
except Exception as e:
    print(e)
    sys.exit(1)
else:
    print("OK")
"@
[System.IO.File]::WriteAllText($tmpPy, $pyCode, (New-Object System.Text.UTF8Encoding($false)))
$compileOutput = & python $tmpPy
$pyExit = $LASTEXITCODE
Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue

if ($pyExit -ne 0 or ($compileOutput -notmatch "OK")) {
  Write-Host $compileOutput
  Die "Python syntax check failed. Backup preserved: $backupBranch / $backupTag"
} else {
  Write-Host "Python syntax check passed."
}

# ---------- Commit & force-push ----------
git -C $Repo add $File
git -C $Repo commit -m "Surgical: rebuild My Assignments tab (remove paste artifact/indent error), fix AgGrid commas, correct LOT regex (^0+). Preserve existing logic."
git -C $Repo push origin $MainBranch --force

Write-Host "Done. Backup branch: $backupBranch ; Tag: $backupTag"
