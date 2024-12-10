"""
Classes and functions around companies bidding for cargoes.
"""

import math
from typing import TYPE_CHECKING, List

from loguru import logger

from mable.transport_operation import SimpleCompany, Bid
from mable.extensions.fuel_emissions import VesselWithEngine

if TYPE_CHECKING:
    from mable.shipping_market import AuctionLedger
    from mable.engine import CompanyHeadquarters


# class TradingCompany:
#     @attrs.define
#     class Data(DataClass):
#         fleet: list[Vessel.Data]
#         name: str
#
#         class Schema(DataSchema):
#             fleet = fields.List(DynamicNestedField())
#             name = fields.Str()
#
#     def __init__(self, fleet, name):
#         """
#         Constructor.
#
#         :param fleet: List of vessels.
#         :type fleet: list[Vessel]
#         :param name: the name of the company
#         :type name: str
#         """
#         super().__init__()
#         # TODO should be requests from centre?
#         self._fleet = fleet
#         self._name = name
#
#     @abstractmethod
#     def inform(self, trades):
#         pass
#
#     @abstractmethod
#     def pre_inform(self, trades, time):
#         pass
#
#     @abstractmethod
#     def receive(self, contracts, auction_ledger=None, *args, **kwargs):
#         pass


class TradingCompany(SimpleCompany[VesselWithEngine]):

    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._headquarters = None

    @property
    def fleet(self):
        """
        :return: The company's fleet.
        :rtype: List[VesselWithEngine]
        """
        return self._fleet

    @property
    def headquarters(self):
        """
        :return: The company's headquarters.
        :rtype: CompanyHeadquarters
        """
        return self._headquarters

    @headquarters.setter
    def headquarters(self, headquarters):
        self._headquarters = headquarters

    def inform(self, trades, *args, **kwargs):
        """
        The shipping company that bids in cargo auctions.

        :param trades: The list of trades.
        :type trades: List[Trade]
        :param args: Not used.
        :param kwargs: Not used.
        :return: The bids of the company
        :rtype: List[Bid]
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        trades_and_costs = [
            (x, proposed_scheduling.costs[x]) if x in proposed_scheduling.costs
            else (x, 0)
            for x in scheduled_trades]
        bids = [Bid(amount=cost, trade=one_trade) for one_trade, cost in trades_and_costs]
        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Allocate a list of trades to the company.

        :param contracts: The list of trades.
        :type contracts: List[Contract]
        :param auction_ledger: Outcomes of all cargo auctions in the round.
        :type auction_ledger: AuctionLedger | None
        :param args: Not used.
        :param kwargs: Not used.
        """
        trades = [one_contract.trade for one_contract in contracts]
        scheduling_proposal = self.propose_schedules(trades)
        self.apply_schedules(scheduling_proposal.schedules)


class MeansCompany(TradingCompany):

    def inform(self, trades, auction_ledger=None, *args, **kwargs):
        """
        The shipping company ...

        :param trades: The list of trades.
        :type trades: list[Trade]
        :param auction_ledger: Outcomes of all cargo auctions in the round.
        :type auction_ledger: AuctionLedger | None
        :param args: Not used.
        :param kwargs: Not used.
        :return: The bids of the company
        :rtype: list[Bid]
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        bids = [Bid(amount=math.inf, trade=one_trade) for one_trade in scheduled_trades]
        return bids


class MCSTCompany(TradingCompany):

    def inform(self, trades, auction_ledger=None, *args, **kwargs):
        """
        The shipping company ...

        :param trades: The list of trades.
        :type trades: list[Trade]
        :param auction_ledger: Outcomes of all cargo auctions in the round.
        :type auction_ledger: AuctionLedger | None
        :param args: Not used.
        :param kwargs: Not used.
        :return: The bids of the company
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        bids = [Bid(amount=math.inf, trade=one_trade) for one_trade in scheduled_trades]
        return bids
