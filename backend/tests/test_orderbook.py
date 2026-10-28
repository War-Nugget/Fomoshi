import pytest

from app.trading.orderbook import Level, parse_orderbook, simulate_fill

RAW = {
    "orderbook_fp": {
        # ascending, as Kalshi sends it
        "yes_dollars": [["0.4000", "50.00"], ["0.4100", "0.00"], ["0.4200", "13.00"]],
        "no_dollars": [["0.5400", "100.00"], ["0.5500", "40.00"], ["0.5600", "17.00"]],
    }
}


def test_parse_sorts_best_first_and_drops_empty_levels():
    book = parse_orderbook(RAW)
    assert book.yes_bids == [Level(420_000, 13), Level(400_000, 50)]
    assert book.no_bids[0] == Level(560_000, 17)


def test_parse_handles_null_side():
    book = parse_orderbook({"orderbook_fp": {"yes_dollars": None, "no_dollars": []}})
    assert book.yes_bids == [] and book.best_ask("no") is None


def test_asks_are_derived_from_the_opposite_bids():
    book = parse_orderbook(RAW)
    assert book.best_ask("yes") == 440_000  # $1 - $0.56 NO bid
    assert book.best_ask("no") == 580_000  # $1 - $0.42 YES bid
    assert [lvl.price for lvl in book.asks("yes")] == [440_000, 450_000, 460_000]


def test_buy_walks_multiple_levels():
    book = parse_orderbook(RAW)
    fill = simulate_fill(book, "yes", "buy", 30)
    assert fill.fills == [Level(440_000, 17), Level(450_000, 13)]
    assert fill.filled == 30 and fill.unfilled == 0
    assert fill.total == 17 * 440_000 + 13 * 450_000
    assert fill.avg_price == round(fill.total / 30)


def test_buy_respects_limit_price():
    book = parse_orderbook(RAW)
    fill = simulate_fill(book, "yes", "buy", 100, limit_price=450_000)
    assert fill.filled == 57 and fill.unfilled == 43  # 17 @ .44 + 40 @ .45


def test_sell_hits_bids_and_respects_limit():
    book = parse_orderbook(RAW)
    fill = simulate_fill(book, "yes", "sell", 20, limit_price=410_000)
    assert fill.fills == [Level(420_000, 13)]  # .40 level is below the limit


def test_partial_fill_when_book_runs_out():
    book = parse_orderbook(RAW)
    fill = simulate_fill(book, "no", "buy", 1_000)
    assert fill.filled == 63 and fill.unfilled == 937


def test_rejects_bad_side():
    with pytest.raises(ValueError):
        simulate_fill(parse_orderbook(RAW), "maybe", "buy", 1)
