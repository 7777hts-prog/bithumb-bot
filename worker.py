import requests

def get_top_moving_coins():
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    res = requests.get(url).json()

    coins = []
    for symbol, data in res['data'].items():
        if symbol == 'date':
            continue

        try:
            change_rate = (float(data['fluctate_rate_24H']))
            volume = float(data['acc_trade_value_24H'])  # 24시간 누적 거래대금 (KRW)

            # 엄격 필터
            if change_rate >= 6 and volume >= 1_000_000_000:  # 변동률 6%↑, 거래대금 10억↑
                coins.append({
                    "symbol": symbol,
                    "price": float(data['closing_price']),
                    "change": round(change_rate, 2),
                    "volume": volume
                })
        except:
            continue

    # 변동률 기준 내림차순 정렬 후 상위 5개만
    coins = sorted(coins, key=lambda x: x['change'], reverse=True)[:5]
    return coins
