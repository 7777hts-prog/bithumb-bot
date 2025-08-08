# -*- coding: utf-8 -*-
import os, math, time
from dataclasses import dataclass
from typing import Dict, Tuple, Any, List

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, request

# ---------------- 기본 설정 ----------------
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "8"))
USER_AGENT = "bithumb-bot/1.0"

# 스캔 임계값
SCAN_TOPN = int(os.getenv("SCAN_TOPN", "5"))
SCAN_MIN_CHANGE = float(os.getenv("SCAN_MIN_CHANGE", "6.0"))                # %
SCAN_MIN_ACC_VALUE = float(os.getenv("SCAN_MIN_ACC_VALUE", "100000000"))    # KRW

# 예측(중기) 임계값
CFG = {
    "TIMEFRAME": os.getenv("PREDICT_TIMEFRAME", "4h"),         # 4h는 캔들 미지원 시 1h로 폴백
    "LOOKBACK": int(os.getenv("PREDICT_LOOKBACK", "150")),
    "VOL_RATIO_MIN": float(os.getenv("VOL_RATIO_MIN", "3.0")),
    "VOL_WINDOW": int(os.getenv("VOL_WINDOW", "34")),
    "PRICE_CHANGE_MAX": float(os.getenv("PRICE_CHANGE_MAX", "6.0")),
    "PRICE_CHANGE_MIN": float(os.getenv("PRICE_CHANGE_MIN", "-2.0")),
    "BB_WINDOW": int(os.getenv("BB_WINDOW", "20")),
    "BB_STD": float(os.getenv("BB_STD", "2.0")),
    "BB_POS_MIN": float(os.getenv("BB_POS_MIN", "0.2")),
    "BB_POS_MAX": float(os.getenv("BB_POS_MAX", "0.65")),
    "OBV_SLOPE_MIN": float(os.getenv("OBV_SLOPE_MIN", "0.0")),
    "OBV_SLOPE_WINDOW": int(os.getenv("OBV_SLOPE_WINDOW", "14")),
    "PREMIUM_MIN": float(os.getenv("PREMIUM_MIN", "0.2")),
    "PREMIUM_MAX": float(os.getenv("PREMIUM_MAX", "1.8")),
    "BUY_RATIO_MIN": float(os.getenv("BUY_RATIO_MIN", "0.58")),
    "SCORE_MIN": float(os.getenv("SCORE_MIN", "60")),
}
GATE_KRW_RATE = float(os.getenv("GATE_KRW_RATE", "1350"))

# HTTP 세션
SESS = requests.Session()
SESS.headers.update({"User-Agent": USER_AGENT})

def http_get_json(url: str, params: dict | None = None) -> dict:
    r = SESS.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

# ---------------- 외부 데이터 ----------------
def bt_tickers() -> dict:
    """
    빗썸 전체 시세 가져오기.
    'ALL_KRW'가 아닌 'ALL'을 사용. 엔드포인트/슬래시 민감해서 다중 시도.
    """
    urls = [
        "https://api.bithumb.com/public/ticker/ALL/",
        "https://api.bithumb.com/public/ticker/ALL",
    ]
    last_err = None
    for u in urls:
        try:
            j = http_get_json(u)
            # 기대 형식: {"status":"0000","data":{...}}
            if isinstance(j, dict) and ("data" in j) and str(j.get("status")) in ("0000", "success", "OK", "200", "None"):
                return j
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Bithumb ticker fetch failed: {last_err}")

def bt_candles(symbol_krw: str, timeframe: str, limit: int) -> list:
    """
    빗썸 캔들: 지원 타임프레임만 가능(1m,3m,5m,10m,30m,1h,6h,12h,24h,1d,1w,1M).
    4h 요청 시 1h로 자동 폴백.
    """
    s = symbol_krw.replace("/", "_")
    for tf in (timeframe, "1h"):
        try:
            url = f"https://api.bithumb.com/public/candlestick/{s}/{tf}"
            j = http_get_json(url)
            data = j.get("data", [])
            if data:
                return data[-limit:]
        except Exception:
            continue
    return []

def bt_orderbook(symbol_krw: str) -> dict:
    s = symbol_krw.replace("/", "_")
    try:
        url = f"https://api.bithumb.com/public/orderbook/{s}"
        return http_get_json(url)
    except Exception:
        return {}

def gate_ticker(symbol_usdt: str) -> dict:
    try:
        arr = http_get_json("https://api.gateio.ws/api/v4/spot/tickers",
                            params={"currency_pair": symbol_usdt})
        return arr[0] if isinstance(arr, list) and arr else {}
    except Exception:
        return {}

# ---------------- 지표 ----------------
def bollinger_pos(close: pd.Series, window: int, nstd: float):
    ma = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = ma + nstd * std
    lower = ma - nstd * std
    pos = (close - lower) / (upper - lower)
    return ma, upper, lower, pos

def obv_series(df: pd.DataFrame) -> pd.Series:
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index)

def linreg_slope(y: pd.Series) -> float:
    x = np.arange(len(y))
    if len(y) < 2: return 0.0
    num = ((x - x.mean()) * (y - y.mean())).sum()
    den = ((x - x.mean())**2).sum()
    return float(num/den) if den else 0.0

# ---------------- 예측 시그널 ----------------
@dataclass
class Signals:
    vol_ratio: float
    price_change: float
    bb_pos: float
    obv_slope: float
    premium_pct: float
    buy_ratio: float

def get_ohlcv_df(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    raw = bt_candles(symbol, timeframe, limit)
    if not raw:
        raise RuntimeError("No OHLCV from Bithumb")
    df = pd.DataFrame(raw, columns=["ts","open","close","high","low","volume"]).astype(float)
    df["time"] = pd.to_datetime(df["ts"], unit="ms")
    return df[["time","open","high","low","close","volume"]]

def compute_signals(df: pd.DataFrame, symbol: str) -> Signals:
    df = df[-CFG["LOOKBACK"]:].copy()
    _, _, _, pos = bollinger_pos(df["close"], CFG["BB_WINDOW"], CFG["BB_STD"])
    df["bb_pos"] = pos

    recent_vol = df["volume"].iloc[-1]
    base_vol = df["volume"].iloc[-CFG["VOL_WINDOW"]-1:-1].mean()
    vol_ratio = (recent_vol / base_vol) if base_vol > 0 else np.nan

    price_change = ((df["close"].iloc[-1] / df["close"].iloc[-2]) - 1.0) * 100.0
    bb_pos_last = float(df["bb_pos"].iloc[-1])
    obv_slope = linreg_slope(obv_series(df)[-CFG["OBV_SLOPE_WINDOW"]:])
    premium_pct, buy_ratio = np.nan, np.nan

    try:
        g = gate_ticker(f"{symbol.split('/')[0]}_USDT")
        if g:
            gate_price_krw = float(g.get("last", 0)) * GATE_KRW_RATE
            if gate_price_krw > 0:
                premium_pct = (float(df['close'].iloc[-1]) / gate_price_krw - 1.0) * 100.0
    except Exception:
        pass

    try:
        ob = bt_orderbook(symbol).get("data", {})
        bids = sum(float(x["quantity"]) for x in ob.get("bids", []))
        asks = sum(float(x["quantity"]) for x in ob.get("asks", []))
        buy_ratio = (bids / (bids + asks)) if (bids + asks) > 0 else np.nan
    except Exception:
        pass

    return Signals(vol_ratio, price_change, bb_pos_last, obv_slope, premium_pct, buy_ratio)

def score_signals(s: Signals) -> Tuple[float, Dict[str, Any]]:
    score = 0.0
    score += 20 if s.vol_ratio >= CFG["VOL_RATIO_MIN"] else 0
    score += 20 if CFG["PRICE_CHANGE_MIN"] <= s.price_change <= CFG["PRICE_CHANGE_MAX"] else 0
    score += 20 if CFG["BB_POS_MIN"] <= s.bb_pos <= CFG["BB_POS_MAX"] else 0
    score += 20 if s.obv_slope >= CFG["OBV_SLOPE_MIN"] else 0
    score += 10 if (not math.isnan(s.premium_pct) and CFG["PREMIUM_MIN"] <= s.premium_pct <= CFG["PREMIUM_MAX"]) else 0
    score += 10 if (not math.isnan(s.buy_ratio) and s.buy_ratio >= CFG["BUY_RATIO_MIN"]) else 0
    return score, {
        "vol_ratio": s.vol_ratio, "price_change": s.price_change, "bb_pos": s.bb_pos,
        "obv_slope": s.obv_slope, "premium_pct": s.premium_pct, "buy_ratio": s.buy_ratio
    }

# ---------------- Flask ----------------
app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"ok": True, "routes": ["/health", "/scan", "/predict?symbols=MNT/KRW,BB/KRW"]})

@app.route("/health")
def health():
    return {"ok": True, "ts": time.time()}

@app.route("/scan")
def scan():
    try:
        data = bt_tickers()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 502

    if "data" not in data or not data["data"]:
        return jsonify({"status":"error","message":"No data from Bithumb"}), 502

    coins: List[Dict[str, Any]] = []
    for sym, d in data["data"].items():
        if sym == "date":
            continue
        try:
            # ALL 응답 필드명: closing_price, acc_trade_value_24H, fluctuate_rate_24H
            chg = float(d.get("fluctate_rate_24H") or d.get("fluctuate_rate_24H") or 0)
            acc = float(d.get("acc_trade_value_24H") or 0)
            price = float(d.get("closing_price") or 0)

            if chg >= SCAN_MIN_CHANGE and acc >= SCAN_MIN_ACC_VALUE:
                coins.append({
                    "symbol": f"{sym}/KRW",   # 표준화
                    "price": price,
                    "change": round(chg, 2),
                    "volume": acc
                })
        except Exception:
            continue

    coins.sort(key=lambda x: x["change"], reverse=True)
    coins = coins[:SCAN_TOPN]

    return jsonify({"status": "success", "count": len(coins), "coins": coins})

@app.route("/predict")
def predict():
    syms_param = request.args.get("symbols")
    if syms_param:
        target = [s.strip() for s in syms_param.split(",") if s.strip()]
    else:
        scan_res = scan().json
        target = [c["symbol"] for c in scan_res.get("coins", [])]

    if not target:
        return jsonify({"status":"success","count":0,"candidates":[], "all":[]})

    results = []
    for sym in target:
        try:
            df = get_ohlcv_df(sym, CFG["TIMEFRAME"], CFG["LOOKBACK"])
            sig = compute_signals(df, sym)
            score, detail = score_signals(sig)
            results.append({
                "symbol": sym,
                "score": round(score, 2),
                "passed": score >= CFG["SCORE_MIN"],
                "signals": {
                    "vol_ratio": None if math.isnan(sig.vol_ratio) else round(sig.vol_ratio, 2),
                    "price_change": None if math.isnan(sig.price_change) else round(sig.price_change, 2),
                    "bb_pos": None if math.isnan(sig.bb_pos) else round(sig.bb_pos, 3),
                    "obv_slope": None if math.isnan(sig.obv_slope) else round(sig.obv_slope, 4),
                    "premium_pct": None if math.isnan(sig.premium_pct) else round(sig.premium_pct, 2),
                    "buy_ratio": None if math.isnan(sig.buy_ratio) else round(sig.buy_ratio, 3),
                },
                "detail": detail
            })
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})

    results.sort(key=lambda x: x.get("score", -1), reverse=True)
    return jsonify({
        "status":"success",
        "timeframe": CFG["TIMEFRAME"],
        "candidates":[r for r in results if r.get("passed")],
        "all": results
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8000")), debug=False)
