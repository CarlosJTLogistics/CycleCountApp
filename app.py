# v1.6.3
# - Assign Counts: added "Paste LOT Numbers (optional)" (CustomerLotReference) and LOT-based assignment
# - Preserves all rules: 20-min lock, Central time CC_TZ, per-pallet only for bulk, TUN=racks, sound/vibration ON, bilingual, post-submit UX, dashboard downloads, Issue Type + Actual Pallet/LOT
# - 'Assign to (name)' is a fixed dropdown (ASSIGN_NAME_OPTIONS) â€” includes Eric (corrected) and Aldo
import os, time, uuid, re, json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
# ===== Constants / Options =====
ASSIGN_NAME_OPTIONS = ["Aldo","Alex","Carlos","Clayton","Cody","Enrique","Eric","James","Jake","Johntai","Karen","Kevin","Luis","Nyahok","Stephanie","Tyteanna"]=current_map
            if st.button(t("save_map"), type="primary", key="map_save_btn"):
                norm = normalize_inventory_df(raw, current_map)
                save_inventory_cache(norm); save_inventory_mapping(current_map)
                st.success(f"Saved mapping and cached {len(norm):,} rows."); st.rerun()
        except Exception as e:
            st.warning(t("excel_err", err=e))



