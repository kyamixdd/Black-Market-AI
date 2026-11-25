"""Multi-timeframe trend analysis and alignment."""
from __future__ import annotations

from typing import Any

from .candle_manager import CandleManager
from .momentum_analyzer import MomentumAnalyzer
from .regime_detector import RegimeDetector
from .volatility_analyzer import VolatilityAnalyzer
from .volume_analyzer import VolumeAnalyzer


class TrendAnalyzer:
    """Analyzes trends across multiple timeframes for confluence."""

    TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

    def __init__(self, candle_manager: CandleManager):
        self.candles = candle_manager

    def analyze(self, market: str, symbol: str) -> dict[str, Any]:
        """Full multi-timeframe analysis."""
        results: dict[str, Any] = {}
        for tf in self.TIMEFRAMES:
            available = len(self.candles.get_series(market, symbol, tf, limit=200))
            if available < 200:
                results[tf] = {
                    "status": "insufficient_data", "available_candles": available,
                    "required_candles": 200, "data_completeness_pct": available / 200 * 100,
                }
                continue

            ohlc = self.candles.get_ohlc(market, symbol, tf, limit=200)
            closes = ohlc["close"]
            highs = ohlc["high"]
            lows = ohlc["low"]
            volumes = ohlc["volume"]

            if len(closes) == 0:
                results[tf] = {"status": "no_data"}
                continue

            rsi = MomentumAnalyzer.rsi(closes)
            macd = MomentumAnalyzer.macd(closes)
            sma20 = MomentumAnalyzer.sma(closes, 20)
            sma50 = MomentumAnalyzer.sma(closes, 50)
            sma200 = MomentumAnalyzer.sma(closes, 200)
            ema9 = MomentumAnalyzer.ema(closes, 9)
            ema21 = MomentumAnalyzer.ema(closes, 21)
            atr = VolatilityAnalyzer.atr(highs, lows, closes)
            bb = VolatilityAnalyzer.bollinger_bands(closes)
            adx = MomentumAnalyzer.adx(highs, lows, closes)
            vol_trend = VolumeAnalyzer.volume_trend(volumes)
            vol_exp = VolumeAnalyzer.volume_expansion(volumes)
            vwap = VolumeAnalyzer.vwap(closes, volumes)
            regime = RegimeDetector.detect(closes, highs, lows)
            vol_regime = RegimeDetector.volatility_regime(closes)

            price = closes[-1]
            trend_strength = self._calc_trend_strength(price, ema9, ema21, sma20, sma50, sma200, adx["adx"])

            results[tf] = {
                "price": float(price),
                "rsi": rsi,
                "macd": macd,
                "sma20": sma20,
                "sma50": sma50,
                "sma200": sma200,
                "ema9": ema9,
                "ema21": ema21,
                "atr": atr,
                "bb": bb,
                "adx": adx["adx"],
                "plus_di": adx["plus_di"],
                "minus_di": adx["minus_di"],
                "vol_trend": vol_trend,
                "vol_expansion": vol_exp,
                "vwap": vwap,
                "regime": regime,
                "vol_regime": vol_regime,
                "trend_strength": trend_strength,
            }

        # Multi-timeframe alignment
        alignment = self._check_alignment(results)
        results["alignment"] = alignment

        return results

    def _calc_trend_strength(self, price: float, ema9: float, ema21: float,
                              sma20: float, sma50: float, sma200: float, adx: float) -> str:
        """Calculate trend strength: STRONG, MODERATE, WEAK, NONE."""
        if price > ema9 > ema21 > sma20 > sma50 > sma200 and adx > 25:
            return "STRONG"
        if price < ema9 < ema21 < sma20 < sma50 < sma200 and adx > 25:
            return "STRONG"
        if price > ema9 > ema21 and sma20 > sma50 and adx > 15:
            return "MODERATE"
        if price < ema9 < ema21 and sma20 < sma50 and adx > 15:
            return "MODERATE"
        if adx < 15:
            return "NONE"
        return "WEAK"

    def _check_alignment(self, results: dict[str, Any]) -> dict[str, Any]:
        """Check trend alignment across timeframes."""
        higher_tfs = ["1h", "4h", "1d"]
        lower_tfs = ["5m", "15m", "30m"]

        higher_regimes = [results[tf].get("regime") for tf in higher_tfs if tf in results and "regime" in results[tf]]
        lower_regimes = [results[tf].get("regime") for tf in lower_tfs if tf in results and "regime" in results[tf]]

        bull_count = sum(1 for r in higher_regimes if r == "BULL_TREND")
        bear_count = sum(1 for r in higher_regimes if r == "BEAR_TREND")

        bull_count_lower = sum(1 for r in lower_regimes if r == "BULL_TREND")
        bear_count_lower = sum(1 for r in lower_regimes if r == "BEAR_TREND")

        alignment = "NEUTRAL"
        if bull_count >= 2 and bull_count_lower >= 2:
            alignment = "BULLISH_ALIGNED"
        elif bear_count >= 2 and bear_count_lower >= 2:
            alignment = "BEARISH_ALIGNED"
        elif bull_count >= 2:
            alignment = "BULLISH_HIGHER"
        elif bear_count >= 2:
            alignment = "BEARISH_HIGHER"
        elif bull_count_lower >= 2:
            alignment = "BULLISH_LOWER"
        elif bear_count_lower >= 2:
            alignment = "BEARISH_LOWER"

        return {
            "alignment": alignment,
            "higher_tf_bull": bull_count,
            "higher_tf_bear": bear_count,
            "lower_tf_bull": bull_count_lower,
            "lower_tf_bear": bear_count_lower,
        }

    def get_trend_summary(self, market: str, symbol: str) -> dict[str, Any]:
        """Quick summary of trend state."""
        results = self.analyze(market, symbol)
        alignment = results.get("alignment", {}).get("alignment", "NEUTRAL")

        # Pick best timeframe with data
        primary_tf = None
        for tf in ["15m", "1h", "4h", "1d"]:
            if tf in results and "trend_strength" in results[tf]:
                primary_tf = tf
                break

        if primary_tf is None:
            return {"status": "no_data"}

        tf_data = results[primary_tf]
        return {
            "primary_tf": primary_tf,
            "price": tf_data["price"],
            "regime": tf_data["regime"],
            "trend_strength": tf_data["trend_strength"],
            "rsi": tf_data["rsi"],
            "adx": tf_data["adx"],
            "alignment": alignment,
        }