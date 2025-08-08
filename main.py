# -*- coding: utf-8 -*-
import os
import math
import time
from dataclasses import dataclass
from typing import Dict, Tuple, Any
import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, request

TIMEOUT = 8
USER_AGENT = "bithumb-bot/1.0"
SCAN_TOPN = 5
SCAN_MIN_CHANGE = 6.0
SCAN_MIN_ACC_VALUE = 100000000
CFG = {
    "TIMEFRAME": "4h",
    "LOOKBACK": 150,
    "VOL_RATIO_MIN": 3.0,
    "VOL_WINDOW": 34,
    "PRICE_CHANGE_MAX": 6.0,
    "PRICE_CHANGE_MIN": -2.0,
    "BB_WINDOW": 20,
    "BB_STD": 2.0,
    "BB_POS_MIN": 0.2,
    "BB_POS_MAX": 0.65,
    "OBV_SLOPE_MIN": 0.0,
    "OBV_SLOPE_WINDOW": 14,
    "PREMIUM_MIN": 0.2,
    "PREMIUM_MAX": 1.8,
    "BUY_RATIO_MIN": 0.58,
    "SCORE_MIN": 60
}
GATE_KRW_RATE = 1350

SESS = requests.Session()
SESS.headers.update({"User-Agent": USER_AGENT})

def http_get_json(url, params=None):
    r = SESS.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def bt_tickers():
    return http_get_json("https://api.bithumb.com/public/tickers")

def bt_candles(symbol, timeframe, limit):
    s = symbol.replace("/", "_")
    url = f"https://api.bithumb.com/public/candlestick/{s}/{timeframe}"
    data = http_get_json(url)
    return data.get("data", [])[-limit:]

def bt_orderbook(symbol):
    s = symbol.replace("/", "_")
    url = f"https://api.bithumb.com/public/orderbook/{s}"
    return http_get_json(url)

def gate_ticker(symbol):
    return http_get_json("https://api.gateio.ws/api/v4/spot/tickers", params={"currency_pair": symbol})[0]

def bollinger_pos(close, window, nstd):
    ma = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = ma + nstd * std
    lower = ma - nstd * std
    pos = (close - lower) / (upper - lower)
    return ma, upper, lower, pos

def obv_series(df):
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index)

def linreg_slope(y):
    x = np.arange(len(y))
    if len(y) < 2:
        return 0.0
    return float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean())**2).sum())

@dataclass
class Signals:
    vol_ratio: float
    price_change: float
    bb_pos: float
    obv_slope: float
    premium_pct: float
    buy_ratio: float

def get_ohlcv_df(symbol, timeframe, limit):
    raw = bt_candles(symbol, timeframe, limit)
    df = pd.DataFrame(raw, columns=["ts","open","close","high","low","volume"]).astype(float)
    df["time"] = pd.to_datetime(df["ts"], unit="ms")
    return df[["time","open","high","low","close","volume"]]

def compute_signals(df, symbol):
    df = df[-CFG["LOOKBACK"]:].copy()
    _, _, _, pos = bollinger_pos(df["close"], CFG["BB_WINDOW"], CFG["BB_STD"])
    df["bb_pos"] = pos
    recent_vol = df["volume"].iloc[-1]
    base_vol = df["volume"].iloc[-CFG["VOL_WINDOW"]-1:-1].mean()
    vol_ratio = recent_vol / base_vol if base_vol > 0 else np.nan
    price_change = ((df["close"].iloc[-1] / df["close"].iloc[-2]) - 1.0) * 100.0
    bb_pos_last = float(df["bb_pos"].iloc[-1])
    obv_slope = linreg_slope(obv_series(df)[-CFG["OBV_SLOPE_WINDOW"]:])
    premium_pct = np.nan
    try:
        g = gate_ticker(f"{symbol.split('/')[0]}_USDT")
        gate_price_krw = float(g["last"]) * GATE_KRW_RATE
        premium_pct = (df["close"].iloc[-1] / gate_price_krw - 1.0) * 100.0
    except:
        pass
    buy_ratio = np.nan
    try:
        ob = bt_orderbook(symbol)
        bids = sum(float(x["quantity"]) for x in ob.get("data", {}).get("bids", []))
        asks = sum(float(x["quantity"]) for x in ob.get("data", {}).get("asks", []))
        buy_ratio = bids / (bids + asks) if (bids + asks) > 0 else np.nan
    except:
        pass
    return Signals(vol_ratio, price_change, bb_pos_last, obv_slope, premium_pct, buy_ratio)

def score_signals(s):
    score = 0
    if s.vol_ratio >= CFG["VOL_RATIO_MIN"]: score += 20
    if CFG["PRICE_CHANGE_MIN"] <= s.price_change <= CFG["PRICE_CHANGE_MAX"]: score += 20
    if CFG["BB_POS_MIN"] <= s.bb_pos <= CFG["BB_POS_MAX"]: score += 20
    if s.obv_slope >= CFG["OBV_SLOPE_MIN"]: score += 20
    if not math.isnan(s.premium_pct) and CFG["PREMIUM_MIN"] <= s.premium_pct <= CFG["PREMIUM_MAX"]: score += 10
    if not math.isnan(s.buy_ratio) and s.buy_ratio >= CFG["BUY_RATIO_MIN"]: score += 10
    return score

app = Flask(__name__)

@app.route("/scan")
def scan():
    data = bt_tickers()
    coins = []
    for sym, d in data["data"].items():
        if sym == "date": continue
        try:
            change_rate = float(d["f24h"]["change"])
            acc_value = float(d["acc_trade_value_24h"])
            if change_rate >= SCAN_MIN_CHANGE and acc_value >= SCAN_MIN_ACC_VALUE:
                coins.append({"symbol": sym,"price": float(d["closing_price"]),"change": round(change_rate, 2),"volume": acc_value})
        except:
            continue
    coins.sort(key=lambda x: x["change"], reverse=True)
    return jsonify({"status": "success","count": len(coins),"coins": coins[:SCAN_TOPN]})

@app.route("/predict")
def predict():
    syms_param = request.args.get("symbols")
    if syms_param:
        target = [s.strip() for s in syms_param.split(",") if s.strip()]
    else:
        target = [c["symbol"] for c in scan().json.get("coins", [])]
    results = []
    for sym in target:
        try:
            df = get_ohlcv_df(sym, CFG["TIMEFRAME"], CFG["LOOKBACK"])
            sig = compute_signals(df, sym)
            score = score_signals(sig)
            results.append({"symbol": sym,"score": round(score, 2),"passed": score >= CFG["SCORE_MIN"]})
        except Exception as e:
            results.append({"symbol": sym, "error": str(e)})
    results.sort(key=lambda x: x.get("score", -1), reverse=True)
    return jsonify({"status": "success","candidates": [r for r in results if r.get("passed")],"all": results})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
