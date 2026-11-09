"""
TradingGuard HITL - Pure Mathematical State Space
Extracts quantitative, distribution-based, and microstructure features
completely detached from human trading narratives (zero ICT, SMC, or subjective geometry).
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd


@dataclass
class StateSpaceConfig:
    vol_window: int = 50
    atr_window: int = 14
    zscore_windows: List[int] = field(default_factory=lambda: [20, 50, 100])
    velocity_horizons: List[int] = field(default_factory=lambda: [3, 8, 21, 55])
    mom_diff_fast: int = 8
    mom_diff_slow: int = 21
    skew_kurt_window: int = 30
    autocorr_window: int = 30
    autocorr_lags: List[int] = field(default_factory=lambda: [1, 2, 3, 5])
    volume_window: int = 20
    vwap_window: int = 50


class MathematicalStateSpace:
    """
    Transforms raw OHLCV market bars into a pure mathematical feature state space.
    All calculations are strictly vectorized, causal (zero lookahead), and normalized.
    """

    def __init__(self, config: Optional[StateSpaceConfig] = None):
        self.cfg = config or StateSpaceConfig()

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all mathematical features on the provided DataFrame.
        Expected columns: ['time', 'open', 'high', 'low', 'close']
        Optional column: ['tick_volume'] or ['real_volume'] or ['volume']
        """
        if len(df) < max(self.cfg.zscore_windows):
            raise ValueError(
                f"DataFrame length ({len(df)}) is less than max required window ({max(self.cfg.zscore_windows)})"
            )

        res = pd.DataFrame(index=df.index)
        res['time'] = df['time']

        o = df['open'].astype(float)
        h = df['high'].astype(float)
        l = df['low'].astype(float)
        c = df['close'].astype(float)

        vol_col = None
        for col in ['tick_volume', 'real_volume', 'volume']:
            if col in df.columns:
                vol_col = df[col].astype(float)
                break
        if vol_col is None:
            vol_col = pd.Series(1.0, index=df.index)

        # -------------------------------------------------------------
        # 1. NORMALIZED VOLATILITY
        # -------------------------------------------------------------
        # Log ratios
        log_hl = np.log(np.maximum(h / np.maximum(l, 1e-12), 1.0))
        log_co = np.log(np.maximum(c / np.maximum(o, 1e-12), 1e-12))

        # Parkinson Volatility (1980): sigma_P = sqrt( 1 / (4 * ln(2)) * ln(H/L)^2 )
        parkinson_var = (1.0 / (4.0 * np.log(2.0))) * (log_hl ** 2)
        res['parkinson_vol'] = np.sqrt(np.maximum(parkinson_var, 0.0))

        # Garman-Klass Volatility (1980):
        # sigma_GK^2 = 0.5 * ln(H/L)^2 - (2*ln(2) - 1) * ln(C/O)^2
        gk_factor = 2.0 * np.log(2.0) - 1.0
        gk_var = 0.5 * (log_hl ** 2) - gk_factor * (log_co ** 2)
        res['gk_vol'] = np.sqrt(np.maximum(gk_var, 0.0))

        # Normalized ATR: True Range / Close
        prev_c = c.shift(1).fillna(c)
        tr1 = h - l
        tr2 = (h - prev_c).abs()
        tr3 = (l - prev_c).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.cfg.atr_window, min_periods=self.cfg.atr_window).mean()
        res['norm_atr'] = atr / np.maximum(c, 1e-12)
        res['atr_raw'] = atr

        # Volatility Regime Z-Score: (GK - rolling_mean) / rolling_std
        gk_mean = res['gk_vol'].rolling(self.cfg.vol_window, min_periods=self.cfg.vol_window).mean()
        gk_std = res['gk_vol'].rolling(self.cfg.vol_window, min_periods=self.cfg.vol_window).std()
        res['vol_regime_z'] = (res['gk_vol'] - gk_mean) / (gk_std + 1e-9)

        # -------------------------------------------------------------
        # 2. MOMENTUM DERIVATIVES
        # -------------------------------------------------------------
        # Log returns
        log_ret = np.log(c / prev_c)
        res['log_return'] = log_ret

        # 1st Derivative (Velocity across multiple scales)
        for k in self.cfg.velocity_horizons:
            # v_k = (C_t - C_{t-k}) / C_{t-k}
            shift_c = c.shift(k)
            res[f'velocity_{k}'] = (c - shift_c) / np.maximum(shift_c, 1e-12)

        # 2nd Derivative (Acceleration: rate of velocity change)
        res['accel_3'] = res['velocity_3'] - res['velocity_3'].shift(1)
        res['accel_8'] = res['velocity_8'] - res['velocity_8'].shift(1)
        res['accel_21'] = res['velocity_21'] - res['velocity_21'].shift(1)

        # 3rd Derivative (Curvature / Jerk proxy)
        res['curvature_8'] = res['accel_8'] - res['accel_8'].shift(1)

        # Normalized Exponential Moving Average Divergence
        ema_fast = c.ewm(span=self.cfg.mom_diff_fast, adjust=False).mean()
        ema_slow = c.ewm(span=self.cfg.mom_diff_slow, adjust=False).mean()
        rolling_std_mom = c.rolling(self.cfg.mom_diff_slow, min_periods=self.cfg.mom_diff_slow).std()
        res['ma_divergence'] = (ema_fast - ema_slow) / (rolling_std_mom + 1e-9)

        # -------------------------------------------------------------
        # 3. DISTRIBUTION Z-SCORES & SHAPE PROPERTIES
        # -------------------------------------------------------------
        for w in self.cfg.zscore_windows:
            w_mean = c.rolling(w, min_periods=w).mean()
            w_std = c.rolling(w, min_periods=w).std()
            res[f'price_zscore_{w}'] = (c - w_mean) / (w_std + 1e-9)

        # Rolling Skewness and Kurtosis of Log Returns
        # Fisher-Pearson coefficient of skewness
        sw = self.cfg.skew_kurt_window
        ret_mean = log_ret.rolling(sw, min_periods=sw).mean()
        ret_centered = log_ret - ret_mean
        m2 = (ret_centered ** 2).rolling(sw, min_periods=sw).mean()
        m3 = (ret_centered ** 3).rolling(sw, min_periods=sw).mean()
        m4 = (ret_centered ** 4).rolling(sw, min_periods=sw).mean()

        denom_skew = (m2 ** 1.5) + 1e-12
        res['skewness_30'] = (m3 / denom_skew).clip(-5.0, 5.0)

        denom_kurt = (m2 ** 2.0) + 1e-12
        # Excess kurtosis (Kurtosis - 3.0)
        res['kurtosis_30'] = ((m4 / denom_kurt) - 3.0).clip(-5.0, 15.0)

        # -------------------------------------------------------------
        # 4. VOLUME IMBALANCE & MICROSTRUCTURE FLOW
        # -------------------------------------------------------------
        vw = self.cfg.volume_window
        vol_mean = vol_col.rolling(vw, min_periods=vw).mean()
        res['volume_ratio'] = vol_col / (vol_mean + 1e-9)

        # Directional Volume Imbalance: (Close - Open) / (High - Low + eps) * VolumeRatio
        candle_body_ratio = (c - o) / ((h - l) + 1e-9)
        res['directional_vol_imb'] = candle_body_ratio * res['volume_ratio']

        # Rolling VWAP & VWAP Disparity Z-Score
        typical_price = (h + l + c) / 3.0
        pv = typical_price * vol_col
        rolling_pv = pv.rolling(self.cfg.vwap_window, min_periods=self.cfg.vwap_window).sum()
        rolling_vol = vol_col.rolling(self.cfg.vwap_window, min_periods=self.cfg.vwap_window).sum()
        vwap = rolling_pv / (rolling_vol + 1e-9)
        vwap_std = (typical_price - vwap).rolling(self.cfg.vwap_window, min_periods=self.cfg.vwap_window).std()
        res['vwap_deviation_z'] = (c - vwap) / (vwap_std + 1e-9)

        # -------------------------------------------------------------
        # 5. MULTI-SCALE AUTOCORRELATION
        # -------------------------------------------------------------
        aw = self.cfg.autocorr_window
        r_sub = log_ret - log_ret.rolling(aw, min_periods=aw).mean()
        var_r = (r_sub ** 2).rolling(aw, min_periods=aw).mean()

        for lag in self.cfg.autocorr_lags:
            cov_lag = (r_sub * r_sub.shift(lag)).rolling(aw, min_periods=aw).mean()
            corr = cov_lag / (var_r + 1e-12)
            res[f'autocorr_lag{lag}'] = corr.clip(-1.0, 1.0)

        # Keep raw prices for backtest execution
        res['open'] = o
        res['high'] = h
        res['low'] = l
        res['close'] = c
        res['volume'] = vol_col

        return res

    @staticmethod
    def get_feature_names() -> List[str]:
        """Returns the list of mathematical features eligible for autonomous rule discovery."""
        return [
            'parkinson_vol',
            'gk_vol',
            'norm_atr',
            'vol_regime_z',
            'velocity_3',
            'velocity_8',
            'velocity_21',
            'velocity_55',
            'accel_3',
            'accel_8',
            'accel_21',
            'curvature_8',
            'ma_divergence',
            'price_zscore_20',
            'price_zscore_50',
            'price_zscore_100',
            'skewness_30',
            'kurtosis_30',
            'volume_ratio',
            'directional_vol_imb',
            'vwap_deviation_z',
            'autocorr_lag1',
            'autocorr_lag2',
            'autocorr_lag3',
            'autocorr_lag5',
        ]
