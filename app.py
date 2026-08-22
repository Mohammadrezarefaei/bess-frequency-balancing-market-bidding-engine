"""Streamlit Web App: BESS Frequency Balancing (FCR / aFRR) & Wholesale Arbitrage Optimizer."""

import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from src.balancing_engine import BESSBalancingMarketEngine

st.set_page_config(
    page_title="BESS Balancing Market Bidding Engine",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Grid-Scale BESS Frequency Balancing & Wholesale Arbitrage Optimizer")
st.markdown("Multi-market mathematical co-optimization stacking revenue across **German Ancillary Services (FCR, aFRR Regelleistung.net)** and **EPEX Spot Day-Ahead Arbitrage** under inverter capacity limits.")

# Sidebar Parameters
st.sidebar.header("🔋 BESS Asset Sizing")
bess_power = st.sidebar.slider("Rated Inverter Power (MW)", 1.0, 20.0, 5.0, 1.0)
bess_capacity = st.sidebar.slider("Storage Energy Capacity (MWh)", 2.0, 40.0, 10.0, 2.0)
deg_cost = st.sidebar.slider("Cycle Throughput Degradation (€/MWh)", 5.0, 25.0, 12.0, 1.0)

st.sidebar.header("📈 Market Clearing Multipliers")
fcr_mult = st.sidebar.slider("FCR Clearing Price Factor", 0.5, 2.0, 1.0, 0.1)
afrr_mult = st.sidebar.slider("aFRR Clearing Price Factor", 0.5, 2.0, 1.0, 0.1)

@st.cache_data
def generate_balancing_data(f_factor, a_factor):
    np.random.seed(42)
    blocks_labels = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]
    fcr_base = np.array([85.0, 110.0, 140.0, 95.0, 165.0, 120.0]) * f_factor
    afrr_pos_base = np.array([55.0, 80.0, 115.0, 70.0, 135.0, 90.0]) * a_factor
    afrr_neg_base = np.array([45.0, 65.0, 90.0, 85.0, 110.0, 75.0]) * a_factor
    spot_base = np.array([65.0, 95.0, 50.0, 40.0, 105.0, 80.0])

    return pd.DataFrame({
        "block_window": blocks_labels,
        "fcr_price_eur_mw_4h": fcr_base,
        "afrr_pos_price_eur_mw_4h": afrr_pos_base,
        "afrr_neg_price_eur_mw_4h": afrr_neg_base,
        "spot_block_avg_eur_mwh": spot_base
    })

df_raw = generate_balancing_data(fcr_mult, afrr_mult)
engine = BESSBalancingMarketEngine(
    bess_power_mw=bess_power,
    bess_capacity_mwh=bess_capacity,
    degradation_cost_eur_mwh=deg_cost
)

df_res, kpis = engine.optimize_bidding(df_raw)

# Top KPIs Row
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Multi-Market Revenue", f"€{kpis['total_revenue_eur']:,.2f} / day")
k2.metric("Spot Arbitrage Baseline", f"€{kpis['spot_only_baseline_eur']:,.2f} / day")
k3.metric("Ancillary Revenue Uplift", f"+{kpis['ancillary_uplift_pct']:.1f}%", delta=f"€{kpis['total_revenue_eur'] - kpis['spot_only_baseline_eur']:,.2f}")
k4.metric("Asset Utilization", f"{bess_power:.0f} MW Committed")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Ancillary Price Clearing & BESS Capacity Stacking")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7))

    x = np.arange(len(df_res))
    ax1.plot(x, df_res["fcr_price_eur_mw_4h"], marker="o", color="#2563EB", lw=2.0, label="FCR Capacity (€/MW/4h)")
    ax1.plot(x, df_res["afrr_pos_price_eur_mw_4h"], marker="s", color="#059669", lw=1.8, label="aFRR Pos Reserve (€/MW/4h)")
    ax1.plot(x, df_res["afrr_neg_price_eur_mw_4h"], marker="^", color="#D97706", lw=1.8, label="aFRR Neg Reserve (€/MW/4h)")
    ax1.plot(x, df_res["spot_block_avg_eur_mwh"], marker="x", color="#DC2626", linestyle="--", lw=1.5, label="Spot Average (€/MWh)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(df_res["block_window"])
    ax1.set_ylabel("Price Level [€]", fontweight="bold")
    ax1.set_title("German Ancillary Products (Regelleistung) vs Wholesale Spot Clearing", fontsize=10, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", frameon=True, fontsize=7.5)

    ax2.bar(x, df_res["fcr_committed_mw"], label="FCR Capacity (MW)", color="#2563EB", alpha=0.85)
    ax2.bar(x, df_res["afrr_pos_committed_mw"], bottom=df_res["fcr_committed_mw"], label="aFRR Pos Reserve (MW)", color="#059669", alpha=0.85)
    ax2.bar(x, df_res["da_discharge_mw"], bottom=df_res["fcr_committed_mw"] + df_res["afrr_pos_committed_mw"], label="Spot Discharge (MW)", color="#DC2626", alpha=0.85)
    ax2.axhline(bess_power, color="#111827", linestyle=":", lw=1.5, label=f"Inverter Rating ({bess_power} MW)")

    ax2.set_xticks(x)
    ax2.set_xticklabels(df_res["block_window"])
    ax2.set_xlabel("4-Hour Product Block [CET]", fontweight="bold")
    ax2.set_ylabel("Allocated Power [MW]", fontweight="bold")
    ax2.set_title("Optimal Dynamic Power Allocation Across 4-Hour Balancing Auctions", fontsize=10, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper right", frameon=True, fontsize=7.5)

    plt.tight_layout()
    st.pyplot(fig)

with col2:
    st.subheader("📑 Commercial P&L Breakdown")
    st.dataframe(
        pd.DataFrame({
            "Revenue Stream": [
                "Primary Reserve (FCR)",
                "Secondary Reserve (aFRR)",
                "EPEX Wholesale Spot",
                "Total Daily Gross P&L",
                "Wholesale Arbitrage Only",
                "Market Stacking Uplift (%)"
            ],
            "Value": [
                f"€{kpis['fcr_revenue_eur']:,.2f}",
                f"€{kpis['afrr_revenue_eur']:,.2f}",
                f"€{kpis['wholesale_da_revenue_eur']:,.2f}",
                f"€{kpis['total_revenue_eur']:,.2f}",
                f"€{kpis['spot_only_baseline_eur']:,.2f}",
                f"+{kpis['ancillary_uplift_pct']:.1f}%"
            ]
        }),
        hide_index=True,
        use_container_width=True
    )
    st.markdown("""
    **Market Structure & Constraints:**
    * **FCR Symmetric Capacity:** Prices primary frequency containment cleared via daily 4-hour auctions on *regelleistung.net*.
    * **aFRR Asymmetric Capacity:** Evaluates positive (upward regulation) and negative (downward regulation) bidding envelopes.
    * **Hardware Limits:** Enforces hard bi-directional inverter capability bounds to eliminate operational overload.
    """)

st.markdown("---")
st.caption("German BESS Ancillary Services (Regelleistung) & Multi-Market Co-Optimization Architecture.")
