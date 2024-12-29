"""
All cargo generation and distribution related classes.
"""
import asyncio
import copy
from abc import abstractmethod
from enum import Enum
from typing import Union, Hashable, TYPE_CHECKING, List, Dict
import math

import attrs
import loguru

from mable.util import JsonAble
from mable.simulation_space.universe import Port
from mable.simulation_environment import SimulationEngineAware


if TYPE_CHECKING:
    from mable.cargo_bidding import TradingCompany
    from mable.transport_operation import ShippingCompany


logger = loguru.logger


class Shipping(SimulationEngineAware):
    """
    A unit to generate and/or manage the occurrence of cargo events.
    """

    def __init__(self, *args, **kwargs):
        """
        Constructor. Calls :py:func:`initialise_trades` with all args and kwargs.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        """
        super().__init__()
        self._all_trades = {}
        self._occurred_trades = {}
        self.initialise_trades(*args, **kwargs)

    @abstractmethod
    def initialise_trades(self, *args, **kwargs):
        """
        Generate all trades.
        """
        pass

    def add_to_all_trades(self, trades):
        """
        Add all trades from a list of trades to the list of known shippable trades.
        :param trades:
        :type trades: List[Time
        :return:
        """
        for one_trade in trades:
            if one_trade.time not in self._all_trades:
                self._all_trades[one_trade.time] = []
            self._all_trades[one_trade.time].append(one_trade)

    def get_trading_times(self):
        """
        All times at which new cargoes will become available.
        :return: list
            The list of times.
        """
        times = list(self._all_trades.keys())
        return times

    def get_trades(self, time):
        """
        Get trades for a specific time.

        :param time: The time.
        :type time: float
        :return: The list of trades.
        :rtype: List[Trade]
        """
        if time in self._occurred_trades:
            all_occurring_trades = self._occurred_trades[time]
        else:
            if time in self._all_trades:
                trades = self._all_trades[time]
                all_occurring_trades = [
                    t for t in trades
                    if self._engine.world.random.choice([0, 1], p=[1 - t.probability, t.probability])]
                logger.info(f"{len(all_occurring_trades)} trades of a total of {len(trades)} trades realised (time: {time}).")
                for one_trade in [t for t in trades if t not in all_occurring_trades]:
                    one_trade.status = TradeStatus.NOT_REALISED
                self._occurred_trades[time] = all_occurring_trades
            else:
                all_occurring_trades = []
        return all_occurring_trades


class TradeStatus(Enum):
    UNKNOWN = 1
    NOT_REALISED = 2
    ACCEPTED = 3
    REJECTED = 4


@attrs.define(kw_only=True)
class Trade(JsonAble):
    """
    A trade opportunity specifying a cargo that shall be transported.

    :param origin_port: The origin of the trade where the cargo has to be picked up.
    :type origin_port: Union[Port, str]
    :param destination_port: The destination of the trade where the cargo has to be dropped off.
    :type destination_port: Union[Port, str]
    :param amount: The amount of cargo to be transported.
    :type amount: float
    :param cargo_type: The type of cargo.
    :type cargo_type: Hashable
    :param time: The time that trade becomes available for allocation or a market etc.
    :type time: int
    """
    origin_port: Union[Port, str]
    destination_port: Union[Port, str]
    amount: float
    cargo_type: Hashable = None
    time: int = 0
    probability: float = 1
    status: TradeStatus = TradeStatus.UNKNOWN

    def to_json(self):
        # noinspection PyTypeChecker
        # Trade is an attrs instance.
        return attrs.asdict(self)


@attrs.define(kw_only=True)
class TimeWindowTrade(Trade):
    """
    A trade with time windows.

    The time windows are represented by four values.
    The first two are the pick-up window consisting of the earliest arrival for pick-up
    and the latest arrival for pick-up.
    The second two are the drop-off window consisting of the earliest arrival for drop-off
    and the latest arrival for drop-off.
    Flexibility or no restrictions are indicated by None.

    :param time_window: The time windows for delivery.
    :type time_window: List[Union[int, None]]

    For additional parameters see :py:class:`Trade`
    """
    time_window: list = [None, None, None, None]

    @property
    def earliest_pickup(self):
        """
        :return: The earliest pick-up time or None if the vessel can arrive at early as desired.
        :rtype: Union[int, None]
        """
        return self.time_window[0]

    @property
    def earliest_pickup_clean(self):
        """
        :return: If None 0 is returned. Otherwise, see :py:func:`earliest_pickup`
        :rtype: int
        """
        time = self.earliest_pickup
        if time is None:
            time = 0
        return time

    @property
    def latest_pickup(self):
        """
        :return: The latest pick-up time or None if the vessel can arrive as late as desired.
        :rtype: Union[int, None]
        """
        return self.time_window[1]

    @property
    def latest_pickup_clean(self):
        """
        :return: If None math.inf is returned. Otherwise, see :py:func:`latest_pickup`
        :type: Union[int, math.inf]
        """
        time = self.latest_pickup
        if time is None:
            time = math.inf
        return time

    @property
    def earliest_drop_off(self):
        """
        :return: The earliest drop-off time or None if the vessel can arrive at early as desired.
        :rtype: Union[int, None]
        """
        return self.time_window[2]

    @property
    def earliest_drop_off_clean(self):
        """
        :return: If None 0 is returned. Otherwise, see :py:func:`earliest_drop_off`
        :rtype: int
        """
        time = self.earliest_drop_off
        if time is None:
            time = 0
        return time

    @property
    def latest_drop_off(self):
        """
        :return: The latest drop-off time or None if the vessel can arrive as late as desired.
        :rtype: Union[int, None]
        """
        return self.time_window[3]

    @property
    def latest_drop_off_clean(self):
        """
        :return: If None math.inf is returned. Otherwise, see :py:func:`latest_drop_off`
        :type: Union[int, math.inf]
        """
        time = self.latest_drop_off
        if time is None:
            time = math.inf
        return time

    def clean_window(self):
        """
        :return: The clean time windows, i.e. a list of the four time points provided by the clean versions:\
        :py:func:`earliest_pickup`, :py:func:`latest_pickup`, :py:func:`earliest_drop_off`\
        and :py:func:`latest_drop_off`.
        """
        return [self.earliest_pickup_clean, self.latest_pickup_clean,
                self.earliest_drop_off_clean, self.latest_drop_off_clean]

    def __hash__(self):
        hash_value = hash(f"super.__hash__(self) {self.time_window}")
        return hash_value


class StaticShipping(Shipping):
    """
    A shipping unit that simply takes a list of trades.
    """

    def initialise_trades(self, *args, **kwargs):
        """
        Initialises the shipping with a list of trades.
        :param args:
            args[0] should be a list of specifications for trades.
        :param kwargs:
            kwargs["class_factory"] should be a :py:class`ClassFactory` or any object with a function
            'generate_trade' to generate a trades from specifications.
        """
        for one_trade in kwargs["fixed_trades"]:
            one_trade["origin_port"] = kwargs["world"].network.get_port(one_trade["origin_port"])
            one_trade["destination_port"] = kwargs["world"].network.get_port(one_trade["destination_port"])
            one_trade = kwargs["class_factory"].generate_trade(**one_trade)
            if one_trade.time not in self._all_trades:
                self._all_trades[one_trade.time] = []
            self._all_trades[one_trade.time].append(one_trade)


class Market:
    """
    A market to distribute the trades.
    """

    @abstractmethod
    def __init__(self, *args, **kwargs):
        super().__init__()

    @staticmethod
    @abstractmethod
    def distribute_trades(time, trades, shipping_companies):
        """
        Conducts the distribution of trades at specified time to the shipping companies.

        :param time: float
            The time of occurrence.
        :param trades: [Trade]
            The list of trades.
        :param shipping_companies: [ShippingCompany]
            The list of shipping companies.
        """
        pass


class SimpleMarket(Market, SimulationEngineAware):
    """
    A simple market which gives the first shipping company all requested trades.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

    @staticmethod
    def distribute_trades(time, trades, shipping_companies):
        """
        Distribute trades to the first shipping company. The company is first informed about all trades and is expected
        to return a list of requested trades which are then directly allocated to the company.
        The shipping
        :param time: float
            The time of occurrence.
        :param trades: [Trade]
            The list of trades.
        :param shipping_companies: [ShippingCompany]
            The list of shipping companies.
        """
        first_company = shipping_companies[0]
        request = first_company.inform(trades)
        first_company.receive(request)


@attrs.define(kw_only=True)
class Contract(JsonAble):
    """
    A cargo transportation contract.
    :param payment: The amount which is paid for the transportation.
    :type payment: float
    :param trade: The trade the company has to transport.
    :type trade: Trade
    """
    payment: float
    trade: Trade
    fulfilled: bool = False

    def copy(self):
        return copy.deepcopy(self)

    def to_json(self):
        # noinspection PyTypeChecker
        # Contract is an attrs instance.
        return attrs.asdict(self)


class AuctionLedger:
    """
    A ledger that collects the auction outcomes.
    """

    def __init__(self, shipping_companies):
        """
        :param shipping_companies: A list of all shipping companies.
        :type shipping_companies: List[TradingCompany]
        """
        self._ledger = {one_company: [] for one_company in shipping_companies}

    @property
    def ledger(self):
        """
        :return: The full ledger as a dict of the trades indexed by the company names.
        :rtype: Dict[ShippingCompany, List[Contract]]
        """
        return self._ledger

    @property
    def sanitised_ledger(self):
        """
        A full copy of the ledger as a dict of the trades indexed by the company names.

        :return: The ledger.
        :rtype: Dict[str, List[Contract]]
        """
        sanitised_ledger = {k.name: [c.copy() for c in self._ledger[k]] for k in self._ledger}
        return sanitised_ledger

    def get_trades_for_company_copy(self, shipping_company):
        """
        The trades allocated to a specific company.

        :param shipping_company: The specific company.
        :type shipping_company: TradingCompany
        :return: A lost of the trades.
        :rtype: List[Trade]
        """
        trades = [copy.deepcopy(t) for t in self[shipping_company]]
        return trades

    def __getitem__(self, shipping_company):
        return self._ledger[shipping_company]

    def __setitem__(self, shipping_company, value):
        """

        :param shipping_company: The shipping company.
        :type shipping_company: TradingCompany
        :param value: The contract.
        :type value: Contract
        :return:
        """
        self._ledger[shipping_company].append(value)

    @property
    def keys(self):
        return self._ledger.keys

@attrs.define
class AuctionAllocationResult:
    ledger: AuctionLedger
    unallocated_trades: List[Trade]


class AuctionMarket(Market, SimulationEngineAware):
    """
    A market which auctions of trades.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

    @staticmethod
    def _get_trade_index(trade, all_trades):
        return all_trades.index(trade)

    @staticmethod
    def inform_future_trades(trades, time, shipping_companies, timeout=60):
        """
        Informs the shipping companies of upcoming trades.

        :param trades: The list of trades.
        :type trades: List[Trade]
        :param time: The time when the trades will be allocated, e.g. auctioned off.
        :param shipping_companies: The list of shipping companies.
        :type shipping_companies: List[ShippingCompany]
        :param timeout: The time to give every company to process the trade information. Default is 60 seconds.
        :type timeout: int
        """
        for current_company in shipping_companies:
            asyncio.run(AuctionMarket._company_pre_inform_timeout(
                current_company, trades, time, timeout=timeout))

    @staticmethod
    def distribute_trades(time, trades, shipping_companies, timeout=60):
        """
        Distribute trades on a second price auction basis. The shipping companies are
        informed (ShippingCompany.receive) of the trades they get allocated via Contracts. All allocations
        are also returned.

        :param time: The time of occurrence.
        :type time: float
        :param trades: The list of trades.
        :type trades: list[Trade]
        :param shipping_companies: The list of shipping companies.
        :type shipping_companies: list[TradingCompany]
        :param timeout: The time to give every company to process the trade information. Default is 60 seconds.
        :type timeout: int
        :return: All allocated traded per company.
        :rtype: AuctionLedger
        """
        all_bids_per_trade = {i: [] for i in range(len(trades))}
        ledger = AuctionLedger(shipping_companies)
        for current_company in shipping_companies:
            company_bids = asyncio.run(AuctionMarket._company_inform_timeout(
                current_company, trades, timeout=timeout))
            for one_bid in company_bids:
                one_bid.company = current_company
                all_bids_per_trade[AuctionMarket._get_trade_index(one_bid.trade, trades)].append(one_bid)
        for one_trade in trades:
            all_bids_for_current_trade = all_bids_per_trade[AuctionMarket._get_trade_index(one_trade, trades)]
            if len(all_bids_for_current_trade) > 0:
                all_bids_for_current_trade_sorted = sorted(all_bids_for_current_trade, key=lambda b: b.amount)
                smallest_bid_company = all_bids_for_current_trade_sorted[0].company
                if len(all_bids_for_current_trade_sorted) > 1:
                    payment = all_bids_for_current_trade_sorted[1].amount
                else:
                    payment = all_bids_for_current_trade_sorted[0].amount
                trade_contract = Contract(payment=payment, trade=one_trade)
                ledger[smallest_bid_company].append(trade_contract)
        return ledger

    @staticmethod
    async def _company_inform_timeout(company, trades, timeout=60):
        company_bids = []
        try:
            company_bids = await asyncio.wait_for(
                asyncio.to_thread(company.inform, trades[:]),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Company {company.name} was stopped from operating 'inform' after {timeout} seconds.")
        except Exception as e:
            logger.error(f"Company {company.name} ran into an exception while operating 'inform'.")
        return company_bids

    @staticmethod
    async def _company_pre_inform_timeout(company, trades, time, timeout=60):
        company_bids = []
        try:
            await asyncio.wait_for(
                asyncio.to_thread(company.pre_inform, trades, time),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Company {company.name} was stopped from operating 'pre_inform' after {timeout} seconds.")
        except Exception as e:
            logger.error(f"Company {company.name} ran into an exception while operating 'pre_inform'.")
        return company_bids
