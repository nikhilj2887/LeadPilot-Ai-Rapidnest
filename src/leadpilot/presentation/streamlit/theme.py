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
[data-testid="stToolbar"], #MainMenu, footer { visibility: hidden; }
[data-testid="stSidebarNav"] { display: none; }
.block-container { max-width: 1440px; padding: 2rem 2.25rem 4rem; }
[data-testid="stSidebar"] { border-right: 1px solid var(--lp-border); }
[data-testid="stSidebar"] .block-container { padding: 1.7rem 1.1rem; }
.lp-brand { padding: .3rem .35rem 1.5rem; }
.lp-brand-name { font-size: 1.15rem; font-weight: 750; letter-spacing: -.025em; }
.lp-brand-mark {
  display:inline-grid; place-items:center; width:2rem; height:2rem; margin-right:.6rem;
  border-radius:.65rem; color:white; background:linear-gradient(135deg,#7968ff,#4c3fe6);
}
.lp-brand-subtitle { color:var(--lp-muted); font-size:.76rem; margin: .4rem 0 0 2.65rem; }
.lp-eyebrow { color:var(--lp-accent); font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; }
.lp-page-header { margin-bottom: 1.35rem; }
.lp-page-header h1 { font-size:2rem; line-height:1.2; letter-spacing:-.04em; margin:.15rem 0 .3rem; }
.lp-page-header p { color:var(--lp-muted); margin:0; font-size:.96rem; }
.lp-section { margin:1.8rem 0 .75rem; }
.lp-section h2 { font-size:1.08rem; letter-spacing:-.02em; margin:0 0 .18rem; }
.lp-section p { color:var(--lp-muted); margin:0; font-size:.86rem; }
.lp-kpi, .lp-panel, .lp-empty, .lp-company-row, .lp-preview {
  border:1px solid var(--lp-border); border-radius:14px;
  background:color-mix(in srgb, var(--secondary-background-color) 82%, transparent);
}
.lp-kpi { padding:1.05rem 1rem; min-height:112px; }
.lp-kpi-top { display:flex; justify-content:space-between; align-items:center; color:var(--lp-muted); font-size:.8rem; }
.lp-kpi-icon { font-size:1rem; }
.lp-kpi-value { font-size:1.75rem; font-weight:750; letter-spacing:-.04em; margin-top:.5rem; }
.lp-panel { padding:1rem 1.1rem; }
.lp-empty { text-align:center; padding:2.5rem 1.5rem; }
.lp-empty-icon { font-size:1.7rem; margin-bottom:.6rem; }
.lp-empty h3 { margin:.15rem 0 .35rem; font-size:1.05rem; }
.lp-empty p { color:var(--lp-muted); max-width:520px; margin:auto; font-size:.9rem; }
.lp-badge {
  display:inline-flex; align-items:center; gap:.35rem; border-radius:999px;
  padding:.22rem .55rem; font-size:.72rem; font-weight:700; white-space:nowrap;
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
div[data-testid="stButton"] button { border-radius:9px; font-weight:650; }
div[data-testid="stForm"] { border:1px solid var(--lp-border); border-radius:14px; padding:1.15rem; }
div[data-testid="stAlert"] { border-radius:12px; }
@media (max-width: 900px) {
  .block-container { padding:1.5rem 1rem 3rem; }
  .lp-page-header h1 { font-size:1.65rem; }
  .lp-kpi { min-height:96px; }
}
</style>
"""


def apply_theme() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
