from app.history import candle_price, to_points, window


def test_candle_price_formats():
    # current format: *_dollars strings
    assert candle_price({"price": {"close_dollars": "0.4200"}}) == 420_000
    # margin-style format: dollars under plain keys, bid/ask objects
    assert candle_price({"price": {"close": "0.4200"}}) == 420_000
    # legacy integer cents
    assert candle_price({"price": {"close": 42}}) == 420_000
    # no trade in the candle -> bid/ask midpoint
    c = {"price": {"close_dollars": None}, "yes_bid": {"close": 40}, "yes_ask": {"close": 44}}
    assert candle_price(c) == 420_000
    c = {"price": {}, "bid": {"close": "0.3000"}, "ask": {"close": "0.3400"}}
    assert candle_price(c) == 320_000
    assert candle_price({"price": None}) is None


def test_points_carry_forward_and_sort():
    candles = [
        {"end_period_ts": 300, "price": {}},
        {"end_period_ts": 100, "price": {"close_dollars": "0.5000"}},
        {"end_period_ts": 200, "price": {"close_dollars": "0.6000"}},
        {"end_period_ts": 50, "price": {}},  # nothing known yet: dropped
    ]
    assert to_points(candles) == [
        {"t": 100, "p": 0.5},
        {"t": 200, "p": 0.6},
        {"t": 300, "p": 0.6},
    ]


def test_window_sizes():
    start, end, interval = window("1d", None)
    assert interval == 1 and end - start == 86_400
    start, end, interval = window("all", None)
    assert interval == 1440 and end - start <= 4000 * 1440 * 60


def test_market_and_event_history_endpoints(client):
    r = client.get("/api/markets/KXSAMPLECPI-01-ABOVE/history", params={"range": "1w"}).json()
    pts = r["points"]
    assert len(pts) > 100 and all(0 < p["p"] < 1 for p in pts)
    assert pts[-1]["p"] == 0.34  # ends at the current price
    assert [p["t"] for p in pts] == sorted(p["t"] for p in pts)

    e = client.get("/api/events/KXSAMPLECHAMP-01/history", params={"range": "1m"}).json()
    assert [s["label"] for s in e["series"]][0] == "Atlanta Comets"
    assert len(e["series"]) == 4 and all(s["points"] for s in e["series"])
    assert client.get("/api/markets/KXSAMPLECPI-01-ABOVE/history?range=5y").status_code == 422
