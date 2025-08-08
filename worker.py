import requests

def get_top_moving_coins():
    url = "https://api.bithumb.com/public/tickers"
    res = requests.get(url, timeout=8).json()

    coins = []
    for symbol, data in res['data'].items():
        if symbol == 'date':
            continue
        try:
            change_rate = float(data['f24h']['change'])
            volume = float(data['acc_trade_value_24h'])
            if change_rate >= 6 and volume > 100000000:
                coins.append({
                    "symbol": symbol,
                    "price": float(data['closing_price']),
                    "change": round(change_rate, 2),
                    "volume": volume
                })
        except Exception:
            continue

    coins = sorted(coins, key=lambda x: x['change'], reverse=True)
    return coins[:5]

def get_predictive_coins():
    coins = get_top_moving_coins()
    if not coins:
        return []

    symbols = [c['symbol'] for c in coins]
    url = "https://bithumb-bot-1.onrender.com/predict"
    r = requests.get(url, params={'symbols': ','.join(symbols)}, timeout=10)
    r.raise_for_status()
    j = r.json()

    return [c['symbol'] for c in j.get('candidates', [])]

if __name__ == "__main__":
    print(get_predictive_coins())
