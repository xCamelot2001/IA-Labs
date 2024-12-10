from typing import List, TYPE_CHECKING

import attrs
from marshmallow import fields

from mable.cargo_bidding import TradingCompany
from mable.transport_operation import ScheduleProposal

if TYPE_CHECKING:
    from mable.extensions.fuel_emissions import VesselWithEngine


class PondPlayer(TradingCompany):

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        if self.headquarters.current_time == 30:
            self.fleet[0].location = self.headquarters.get_network_port_or_default(
                "Helgoland-c47a1ee22838", None)
            self.fleet[1].location = self.headquarters.get_network_port_or_default(
                "Colombo-04104bbca75f", None)


class MyArchEnemy(TradingCompany):

    def __init__(self, fleet, name, profit_factor=1.65):
        """
        :param fleet: The companies fleet.
        :type fleet: List[VesselWithEngine]
        :param name: The companies name.
        :type name: str
        :param profit_factor: The companies profit factor, i.e. factor applied to cost to determine bids.
        :type profit_factor: float
        """
        super().__init__(fleet, name)
        self._profit_factor = profit_factor

    @attrs.define
    class Data(TradingCompany.Data):
        profit_factor: float = 1.65

        class Schema(TradingCompany.Data.Schema):
            profit_factor = fields.Float(default=1.65)

    def propose_schedules(self, trades):
        schedules = {}
        costs = {}
        scheduled_trades = []
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self.fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    loading_time = current_vessel.get_loading_time(current_trade.cargo_type, current_trade.amount)
                    loading_costs = current_vessel.get_loading_consumption(loading_time)
                    unloading_costs = current_vessel.get_unloading_consumption(loading_time)
                    travel_distance = self.headquarters.get_network_distance(
                        current_trade.origin_port, current_trade.destination_port)
                    travel_time = current_vessel.get_travel_time(travel_distance)
                    travel_cost = current_vessel.get_laden_consumption(travel_time, current_vessel.speed)
                    total_costs = loading_costs + unloading_costs + travel_cost
                    costs[current_trade] = total_costs * self._profit_factor
                    schedules[current_vessel] = new_schedule
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, costs)


class TheScheduler(TradingCompany):

    def __init__(self, fleet, name, profit_factor=1.65):
        """
        :param fleet: The companies fleet.
        :type fleet: List[VesselWithEngine]
        :param name: The companies name.
        :type name: str
        :param profit_factor: The companies profit factor, i.e. factor applied to cost to determine bids.
        :type profit_factor: float
        """
        super().__init__(fleet, name)
        self._profit_factor = profit_factor

    @attrs.define
    class Data(TradingCompany.Data):
        profit_factor: float = 1.65

        class Schema(TradingCompany.Data.Schema):
            profit_factor = fields.Float(default=1.65)

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        trades = [one_contract.trade for one_contract in contracts]
        scheduling_proposal = self.propose_schedules(trades, False)
        _ = self.apply_schedules(scheduling_proposal.schedules)

    def propose_schedules(self, trades, calculate_cost=True):
        schedules = {}
        scheduled_trades = []
        costs = {}
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self._fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                insertion_points = new_schedule.get_insertion_points()[-8:]
                shortest_schedule = None
                for k in range(len(insertion_points)):
                    idx_pick_up = insertion_points[k]
                    insertion_point_after_idx_k = insertion_points[k:]
                    for m in range(len(insertion_point_after_idx_k)):
                        idx_drop_off = insertion_point_after_idx_k[m]
                        new_schedule_test = new_schedule.copy()
                        new_schedule_test.add_transportation(current_trade, idx_pick_up, idx_drop_off)
                        if (shortest_schedule is None
                                or new_schedule_test.completion_time() < shortest_schedule.completion_time()):
                            if new_schedule_test.verify_schedule():
                                shortest_schedule = new_schedule_test
                if shortest_schedule is not None:
                    total_costs = self.predict_cost(current_vessel, current_trade)
                    schedules[current_vessel] = shortest_schedule
                    costs[current_trade] = total_costs * self._profit_factor
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, costs)

    def predict_cost(self, vessel, trade):
        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        loading_costs = vessel.get_loading_consumption(loading_time)
        unloading_costs = vessel.get_unloading_consumption(loading_time)
        travel_distance = self.headquarters.get_network_distance(
            trade.origin_port, trade.destination_port)
        travel_time = vessel.get_travel_time(travel_distance)
        travel_cost = vessel.get_laden_consumption(travel_time, vessel.speed)
        total_cost = loading_costs + unloading_costs + travel_cost
        return total_cost
