"""Automated Pytest Suite for BESS Frequency Balancing Engine."""

import pytest
import numpy as np
import pandas as pd
from src.balancing_engine import BESSBalancingMarketEngine


@pytest.fixture
def sample_6block_market_data():
  return pd.DataFrame({
      "block_window": ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"],
      "fcr_price_eur_mw_4h": [85.0, 110.0, 140.0, 95.0, 165.0, 120.0],
      "afrr_pos_price_eur_mw_4h": [55.0, 80.0, 115.0, 70.0, 135.0, 90.0],
      "afrr_neg_price_eur_mw_4h": [45.0, 65.0, 90.0, 85.0, 110.0, 75.0],
      "spot_block_avg_eur_mwh": [65.0, 95.0, 50.0, 40.0, 105.0, 80.0],
  })


def test_revenue_stacking_uplift(sample_6block_market_data):
  engine = BESSBalancingMarketEngine(bess_power_mw=5.0)
  df_res, kpis = engine.optimize_bidding(sample_6block_market_data)

  assert len(df_res) == 6
  assert kpis["total_revenue_eur"] > kpis["spot_only_baseline_eur"]
  assert kpis["ancillary_uplift_pct"] > 0.0


def test_power_capacity_inverter_limits(sample_6block_market_data):
  engine = BESSBalancingMarketEngine(bess_power_mw=5.0)
  df_res, _ = engine.optimize_bidding(sample_6block_market_data)

  for _, row in df_res.iterrows():
    dis_sum = (
        row["fcr_committed_mw"]
        + row["afrr_pos_committed_mw"]
        + row["da_discharge_mw"]
    )
    ch_sum = (
        row["fcr_committed_mw"]
        + row["afrr_neg_committed_mw"]
        + row["da_charge_mw"]
    )
    assert dis_sum <= 5.0 + 1e-5
    assert ch_sum <= 5.0 + 1e-5
