"""
BESS German Ancillary Services (FCR / aFRR) & Wholesale Arbitrage Co-Optimizer.
Maximizes revenue stacking across 4-hour Regelleistung products and EPEX Spot Day-Ahead.
"""

from typing import Dict, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import linprog


class BESSBalancingMarketEngine:

  def __init__(
      self,
      bess_power_mw: float = 5.0,
      bess_capacity_mwh: float = 10.0,
      degradation_cost_eur_mwh: float = 12.0,
  ):
    self.bess_power_mw = bess_power_mw
    self.bess_capacity_mwh = bess_capacity_mwh
    self.degradation_cost_eur_mwh = degradation_cost_eur_mwh

  def optimize_bidding(
      self, df_market: pd.DataFrame
  ) -> Tuple[pd.DataFrame, Dict[str, float]]:
    df = df_market.copy()
    num_blocks = len(df)
    num_vars = 5 * num_blocks  # [P_fcr, P_afrr_pos, P_afrr_neg, P_da_ch, P_da_dis]

    fcr_p = df["fcr_price_eur_mw_4h"].values
    afrr_pos_p = df["afrr_pos_price_eur_mw_4h"].values
    afrr_neg_p = df["afrr_neg_price_eur_mw_4h"].values
    spot_avg = df["spot_block_avg_eur_mwh"].values

    # Objective Function (Minimize -Revenue)
    c = np.zeros(num_vars)
    for b in range(num_blocks):
      c[b] = -fcr_p[b]
      c[num_blocks + b] = -afrr_pos_p[b]
      c[2 * num_blocks + b] = -afrr_neg_p[b]
      c[3 * num_blocks + b] = spot_avg[b] * 4.0
      c[4 * num_blocks + b] = -(
          (spot_avg[b] - self.degradation_cost_eur_mwh) * 4.0
      )

    # Physical Inverter Capability Constraints
    A_ub = []
    b_ub = []

    for b in range(num_blocks):
      # Upward / Discharge headroom (FCR + aFRR+ + DA Dis <= P_max)
      row_dis = np.zeros(num_vars)
      row_dis[b] = 1.0
      row_dis[num_blocks + b] = 1.0
      row_dis[4 * num_blocks + b] = 1.0
      A_ub.append(row_dis)
      b_ub.append(self.bess_power_mw)

      # Downward / Charge headroom (FCR + aFRR- + DA Ch <= P_max)
      row_ch = np.zeros(num_vars)
      row_ch[b] = 1.0
      row_ch[2 * num_blocks + b] = 1.0
      row_ch[3 * num_blocks + b] = 1.0
      A_ub.append(row_ch)
      b_ub.append(self.bess_power_mw)

    A_ub = np.array(A_ub)
    b_ub = np.array(b_ub)
    bounds = [(0.0, self.bess_power_mw) for _ in range(num_vars)]

    # Solve Linear Program (HiGHS)
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
      raise RuntimeError(f"Multi-Market Optimization failed: {res.message}")

    fcr_alloc = res.x[:num_blocks]
    afrr_pos_alloc = res.x[num_blocks : 2 * num_blocks]
    afrr_neg_alloc = res.x[2 * num_blocks : 3 * num_blocks]
    da_ch_alloc = res.x[3 * num_blocks : 4 * num_blocks]
    da_dis_alloc = res.x[4 * num_blocks :]

    df["fcr_committed_mw"] = fcr_alloc
    df["afrr_pos_committed_mw"] = afrr_pos_alloc
    df["afrr_neg_committed_mw"] = afrr_neg_alloc
    df["da_charge_mw"] = da_ch_alloc
    df["da_discharge_mw"] = da_dis_alloc

    # Financial Breakdowns
    fcr_rev = float(np.sum(fcr_alloc * fcr_p))
    afrr_rev = float(
        np.sum(afrr_pos_alloc * afrr_pos_p + afrr_neg_alloc * afrr_neg_p)
    )
    da_rev = float(
        np.sum((da_dis_alloc * spot_avg - da_ch_alloc * spot_avg) * 4.0)
    )
    total_gross_profit = float(-res.fun)

    # Benchmark: Pure Wholesale Spot Arbitrage Only
    c_spot = np.zeros(2 * num_blocks)
    c_spot[:num_blocks] = spot_avg * 4.0
    c_spot[num_blocks:] = -(spot_avg - self.degradation_cost_eur_mwh) * 4.0

    A_spot = np.zeros((num_blocks, 2 * num_blocks))
    for b in range(num_blocks):
      A_spot[b, b] = 1.0
      A_spot[b, num_blocks + b] = 1.0
    b_spot = np.full(num_blocks, self.bess_power_mw)
    bounds_spot = [(0.0, self.bess_power_mw) for _ in range(2 * num_blocks)]

    res_spot = linprog(
        c_spot, A_ub=A_spot, b_ub=b_spot, bounds=bounds_spot, method="highs"
    )
    spot_only_profit = float(-res_spot.fun)

    uplift_pct = (
        ((total_gross_profit - spot_only_profit) / spot_only_profit) * 100.0
        if spot_only_profit > 0
        else 100.0
    )

    kpis = {
        "fcr_revenue_eur": round(fcr_rev, 2),
        "afrr_revenue_eur": round(afrr_rev, 2),
        "wholesale_da_revenue_eur": round(da_rev, 2),
        "total_revenue_eur": round(total_gross_profit, 2),
        "spot_only_baseline_eur": round(spot_only_profit, 2),
        "ancillary_uplift_pct": round(uplift_pct, 1),
    }

    return df, kpis
