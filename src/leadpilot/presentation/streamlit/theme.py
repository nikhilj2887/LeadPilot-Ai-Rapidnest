from __future__ import annotations

import streamlit as st

APP_CSS = """
<style>
:root {
  --lp-accent: #6d5dfc;
  --lp-accent-soft: rgba(109, 93, 252, .12);
  --lp-border: rgba(125, 125, 145, .22);
  --lp-muted: #8b8b9e;
}
[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stAppViewContainer"] > .main .block-container {
  width:100%; max-width:1560px; padding:2rem clamp(1.25rem, 3vw, 3rem) 4rem;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--lp-border); }
[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
  position:absolute; top:.5rem; right:.5rem; z-index:2;
}
[data-testid="stSidebar"] .block-container { padding:.25rem 1rem 1.7rem; }
[data-testid="stSidebar"] [data-testid="stImage"] {
  max-width:220px; margin:-1rem auto 1rem; padding:.55rem;
  border:1px solid rgba(255,255,255,.72); border-radius:14px; background:#fff;
}
[data-testid="stSidebar"] [data-testid="stImage"] img {
  width:100%; max-height:170px; object-fit:contain;
}
.lp-product-subtitle {
  margin:-.45rem 0 1rem; color:var(--lp-muted); font-size:.82rem;
  line-height:1.4; text-align:center;
}
.lp-organization {
  margin:.15rem 0 .65rem; padding:.85rem .9rem;
  border:1px solid rgba(125,125,145,.28); border-radius:11px;
  background:rgba(109,93,252,.07); overflow:hidden;
}
.lp-organization-label {
  color:var(--lp-muted); font-size:.72rem; font-weight:700;
  letter-spacing:.06em; line-height:1.2; text-transform:uppercase;
}
.lp-organization-name {
  margin-top:.32rem; color:rgba(250,250,255,.96); font-size:.9rem;
  font-weight:650; line-height:1.35; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap;
}
.lp-user {
  display:flex; flex-direction:column; gap:.18rem; margin:.7rem 0 .45rem;
  padding:.72rem .85rem; border-top:1px solid var(--lp-border);
  border-bottom:1px solid var(--lp-border);
}
.lp-user strong {
  color:rgba(250,250,255,.96); font-size:.86rem;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.lp-user span { color:var(--lp-muted); font-size:.75rem; }
.lp-login-shell {
  max-width:560px; margin:7vh auto 0;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] {
  width:100%; margin:0 0 .9rem;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div {
  width:100%; min-width:0;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"]:focus-visible {
  outline:3px solid rgba(109,93,252,.72); outline-offset:2px;
}
.lp-eyebrow { color:var(--lp-accent); font-size:.8rem; font-weight:700; letter-spacing:.035em; }
.lp-page-header { margin-bottom: 1.35rem; }
.lp-page-header h1 { font-size:clamp(1.8rem,2.4vw,2.15rem); line-height:1.2; letter-spacing:-.035em; margin:.2rem 0 .4rem; }
.lp-page-header p { color:var(--lp-muted); margin:0; font-size:1rem; line-height:1.55; }
.lp-section { margin:1.8rem 0 .75rem; }
.lp-section h2 { font-size:1.25rem; line-height:1.35; letter-spacing:-.02em; margin:0 0 .25rem; }
.lp-section p { color:var(--lp-muted); margin:0; font-size:.92rem; line-height:1.5; }
.lp-kpi, .lp-panel, .lp-empty, .lp-company-row, .lp-preview {
  border:1px solid var(--lp-border); border-radius:14px;
  background:color-mix(in srgb, var(--secondary-background-color) 82%, transparent);
}
.lp-kpi { padding:1.15rem; min-height:126px; height:100%; }
.lp-kpi-top { display:flex; justify-content:space-between; align-items:center; gap:.5rem; color:var(--lp-muted); font-size:.9rem; line-height:1.35; }
.lp-kpi-icon { font-size:1.05rem; }
.lp-kpi-value { font-size:2rem; line-height:1.1; font-weight:750; letter-spacing:-.04em; margin-top:.7rem; }
.lp-score { padding:1.15rem; min-height:190px; height:100%; }
.lp-score-value { font-size:2rem; font-weight:780; margin:.5rem 0; }
.lp-score p { color:var(--lp-muted); font-size:.84rem; line-height:1.45; margin:.65rem 0 0; }
.lp-progress { height:.42rem; overflow:hidden; border-radius:999px; background:var(--lp-border); margin-top:.75rem; }
.lp-progress span { display:block; height:100%; background:var(--lp-accent); border-radius:inherit; }
.lp-report-card { border:1px solid var(--lp-border); border-radius:12px; padding:1rem; margin:.5rem 0; }
.lp-report-card p { margin:.35rem 0; line-height:1.5; }
.lp-panel { padding:1rem 1.1rem; }
.lp-empty { text-align:center; padding:2.5rem 1.5rem; }
.lp-empty-icon { font-size:1.7rem; margin-bottom:.6rem; }
.lp-empty h3 { margin:.15rem 0 .35rem; font-size:1.05rem; }
.lp-empty p { color:var(--lp-muted); max-width:520px; margin:auto; font-size:.9rem; }
.lp-badge {
  display:inline-flex; align-items:center; gap:.35rem; border-radius:999px;
  padding:.28rem .62rem; font-size:.78rem; font-weight:700; white-space:nowrap;
  border:1px solid currentColor;
}
.lp-dot { width:.4rem; height:.4rem; border-radius:50%; background:currentColor; }
.lp-new { color:#4d8df7; }.lp-researching { color:#9b7af7; }
.lp-qualified { color:#16a085; }.lp-contacted { color:#d78b16; }
.lp-proposal { color:#d65cbd; }.lp-won { color:#35a853; }.lp-lost { color:#d65a62; }
.lp-healthy { color:#27a65a; }.lp-unhealthy { color:#d65a62; }
.lp-label { color:var(--lp-muted); font-size:.75rem; margin-bottom:.25rem; }
.lp-value { font-size:.92rem; font-weight:600; overflow-wrap:anywhere; }
.lp-meta { color:var(--lp-muted); font-size:.78rem; }
.lp-divider { height:1px; background:var(--lp-border); margin:1rem 0; }
.lp-form-section {
  border-top:1px solid var(--lp-border); padding-top:1.1rem; margin-top:1.15rem;
}
.lp-form-section h3 { font-size:.98rem; margin:0 0 .15rem; }
.lp-form-section p { color:var(--lp-muted); font-size:.78rem; margin:0 0 .6rem; }
.lp-coming { color:var(--lp-muted); font-size:.74rem; text-transform:uppercase; letter-spacing:.07em; font-weight:700; }
.lp-preview { padding:1.1rem; min-height:138px; }
.lp-preview h3 { font-size:.96rem; margin:.6rem 0 .3rem; }
.lp-preview p { color:var(--lp-muted); font-size:.82rem; }
.lp-health { font-size:.75rem; color:var(--lp-muted); padding:.2rem .35rem; }
.lp-health strong { color:var(--text-color); }
.lp-attribution {
  margin-top:1.15rem; padding-top:.8rem; border-top:1px solid var(--lp-border);
  color:var(--lp-muted); font-size:.72rem; letter-spacing:.02em;
}
div[data-testid="stButton"] button { border-radius:9px; min-height:2.65rem; font-size:.92rem; font-weight:650; }
[data-testid="stDataFrame"] { font-size:.9rem; }
[data-testid="stSidebar"] [role="radiogroup"] {
  width:100%; gap:.35rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
  box-sizing:border-box; width:100%; min-width:0; min-height:2.75rem;
  margin:0; padding:.35rem .8rem .35rem .9rem; gap:.72rem;
  border:1px solid transparent; border-radius:10px;
  color:rgba(235,235,245,.82); cursor:pointer;
  transition:background-color .16s ease, border-color .16s ease, box-shadow .16s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label p {
  margin:0; overflow:hidden; color:inherit; font-weight:550;
  line-height:1.3; text-overflow:ellipsis; white-space:nowrap;
}
[data-testid="stSidebar"] [role="radiogroup"] label:not(:has(input:checked)):hover {
  background:rgba(109,93,252,.09); border-color:rgba(109,93,252,.18);
  color:rgba(250,250,255,.94);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background:#29265f; border-color:rgba(132,116,255,.48);
  box-shadow:inset 4px 0 0 #7c6cff; color:#fff;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
  font-weight:680;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) > div > div > div:first-child {
  background:#7c6cff !important; border-color:#a79cff !important;
  box-shadow:0 0 0 2px rgba(124,108,255,.2) !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label:not(:has(input:checked)) > div > div > div:first-child {
  background:transparent !important;
  border:1.5px solid rgba(235,235,245,.62) !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:focus-visible) {
  outline:3px solid rgba(109,93,252,.72); outline-offset:2px;
}
div[data-testid="stForm"] { border:1px solid var(--lp-border); border-radius:14px; padding:1.15rem; }
div[data-testid="stAlert"] { border-radius:12px; }
@media (max-width: 900px) {
  [data-testid="stAppViewContainer"] > .main .block-container { padding:1.5rem 1rem 3rem; }
  .lp-page-header h1 { font-size:1.65rem; }
  .lp-kpi { min-height:108px; }
  .lp-score { min-height:170px; }
}
@media (max-width: 1100px) {
  [data-testid="stHorizontalBlock"] { flex-wrap:wrap; gap:.8rem; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex:1 1 190px; min-width:min(190px, 100%);
  }
}
</style>
"""


def apply_theme() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
