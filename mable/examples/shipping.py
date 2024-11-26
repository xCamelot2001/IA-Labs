from typing import List

from mable.shipping_market import TimeWindowTrade


def example_trades_1():
    """
    A list of five specified trades.

    Month 1:
        - Aberdeen to La Plata (amount: 100000)
        - Hartlepool to Rotterdam (amount: 210000)
    Month 2:
        - Rostock to Singapore (amount: 100000, earliest drop-off after day 90)
        - Jeddah to Texas City (amount: 100000)
    Month 3:
        - Singapore to Panama City (amount: 100000, latest pick-up before day 100)

    :return: The list of trades.
    :rtype: List[TimeWindowTrade]
    """
    trade_1 = TimeWindowTrade(
        origin_port="Aberdeen-f8ea5ddd09c3",
        destination_port="La Plata-c06d7cba9b45",
        amount=100000,
        cargo_type="Oil",
        time=30 * 24)
    trade_2 = TimeWindowTrade(
        origin_port="Hartlepool-3ef4e9aa5ca8",
        destination_port="Rotterdam-92c070ce8e92",
        amount=210000,
        cargo_type="Oil",
        time=30 * 24)
    trade_3 = TimeWindowTrade(
        origin_port="Rostock-3757c4df2366",
        destination_port="Singapore-bfe15a9e31a0",
        amount=100000,
        cargo_type="Oil",
        time=60 * 24,
        time_window=[None, None, 90 * 24, None])
    trade_4 = TimeWindowTrade(
        origin_port="Singapore-bfe15a9e31a0",
        destination_port="Panama City-6a366b46b9bd",
        amount=100000,
        cargo_type="Oil",
        time=90 * 24,
        time_window=[None, 100 * 24, None, None])
    trade_5 = TimeWindowTrade(
        origin_port="Jeddah-17dce7ee2e7d",
        destination_port="Texas City-28cb23375401",
        amount=100000,
        cargo_type="Oil",
        time=60 * 24)
    trades = [trade_1, trade_2, trade_3, trade_4, trade_5]
    return trades
