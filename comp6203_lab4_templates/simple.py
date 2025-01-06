from mable.cargo_bidding import TradingCompany, Bid
from mable.transport_operation import ScheduleProposal

class Company5(TradingCompany):
    def __init__(self, fleet, name, profit_factor=1.2):
        """
        :param fleet: List of vessels in the company's fleet.
        :param name: Name of the company.
        :param profit_factor: Multiplier applied to costs to determine bid prices.
        """
        super().__init__(fleet, name)
        self.profit_factor = profit_factor

    def propose_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        costs = {}

        for trade in trades:
            best_vessel = None
            best_schedule = None
            best_cost = float('inf')

            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule).copy()
                insertion_points = current_schedule.get_insertion_points()[-8:]  # Consider last 8 points

                for pickup_idx in insertion_points:
                    for dropoff_idx in insertion_points:
                        if dropoff_idx < pickup_idx:
                            continue
                        try:
                            trial_schedule = current_schedule.copy()
                            trial_schedule.add_transportation(trade, pickup_idx, dropoff_idx)

                            if trial_schedule.verify_schedule():
                                cost = self.calculate_cost(vessel, trade)
                                if cost < best_cost:
                                    best_vessel = vessel
                                    best_schedule = trial_schedule
                                    best_cost = cost
                        except Exception:
                            continue

            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(trade)
                costs[trade] = best_cost

        return ScheduleProposal(schedules, scheduled_trades, costs)

    def inform(self, trades, *args, **kwargs):
        try:
            proposed_schedules = self.propose_schedules(trades)
            bids = []

            for trade in proposed_schedules.scheduled_trades:
                cost = proposed_schedules.costs[trade]
                bid_amount = cost * self.profit_factor  # Apply profit margin
                bids.append(Bid(amount=bid_amount, trade=trade))

            return bids
        except Exception as e:
            print(f"[inform] Error: {e}")
            return []

    def calculate_cost(self, vessel, trade):
        distance = self._distances.get(
            (trade.origin_port, trade.destination_port), None
        )
        if distance is None:
            distance = self.headquarters.get_network_distance(
                trade.origin_port, trade.destination_port
            )
            self._distances[(trade.origin_port, trade.destination_port)] = distance

        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        travel_time = vessel.get_travel_time(distance)

        time_penalty = max(
            0, trade.earliest_drop_off - (trade.time_window[1] - trade.time_window[0])
        )

        total_cost = (
            vessel.get_cost(vessel.get_loading_consumption(loading_time))
            + vessel.get_cost(vessel.get_unloading_consumption(loading_time))
            + vessel.get_cost(vessel.get_laden_consumption(travel_time, vessel.speed))
            + time_penalty
        )
        return total_cost

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.propose_schedules(trades)
        _ = self.apply_schedules(scheduling_proposal.schedules)
