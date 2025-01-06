from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal, Vessel, SimpleVessel
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade
from mable.extensions.fuel_emissions import VesselWithEngine
from mable.examples import environment, fleets

# import mable.simulation_space.universe


class Company5(TradingCompany):
    def __init__(self, fleet, name):
        """
        Initialize the company with a fleet and a name.
        """
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None
        self._distances = {}
        self.competitor_data = {}
        self.current_schedule = {}
        self.future_trades = []
        self.opponent_data = {}

    def pre_inform(self, trades, time):
        """
        Inform the company of the trades available for bidding.
        """
        self._future_trades = trades
        self._future_auction_time = time
        print(f"Future trades: {trades}, Time: {time}")

    def inform(self, trades, *args, **kwargs):
        """
        Called by the market to request bids for the currently auctioned trades.
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        bids = []

        for trade in scheduled_trades:
            cost_estimate = proposed_scheduling.costs.get(trade, 0.0)
            bid_amount = self.create_bid(cost_estimate, trade)
            bids.append(Bid(amount=bid_amount, trade=trade))

        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Receive the contracts and update the schedule.
        """
        if auction_ledger:
            for company, won_trades in auction_ledger.items():
                # if company != self.name:
                print(f"Competitor {company} won trades: {won_trades}")

        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.assign_schedules(trades)
        for contract in contracts:
            print(f"contract.trade{contract.trade}")
            print(f"scheduled_trades{scheduling_proposal.scheduled_trades}")
            if contract.trade in scheduling_proposal.scheduled_trades:
                contract.fulfilled = True
        self.current_schedule = contracts

    def find_competing_vessels(self, current_trade):
        """
        Find the closest vessel to the trade's origin port for each competing company.
        """
        competing_vessels = {}

        for company in self.headquarters.get_companies():
            if company == self:
                continue
            # for every company find the closest vessel to the trade's origin port
            print(f"nidejiandui:{company.fleet}")
            print(f"nidetrade:{current_trade}")
            closest_vessel = min(
                company.fleet,
                key=lambda v: self.headquarters.get_network_distance(
                    v.location, current_trade.origin_port
                ),
            )
            # add the closest vessel to the competing vessels dictionary
            competing_vessels[company] = closest_vessel
        return competing_vessels

    def propose_schedules(self, trades):
        """
        Propose schedules for the trades, optimizing for maximum fulfillment and minimum penalties. Bidding phase.
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []
        costs = {}

        # Step 1: Sort trades by priority (profitability and time constraints)
        trades = sorted(
            trades,
            key=lambda t: (
                t.amount / max(1, t.time_window[1] - t.time_window[0]),
                -t.earliest_pickup,
            ),
            reverse=True,
        )

        # Step 2: Assign trades to vessels
        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            best_score = float("-inf")
            best_cost = float("inf")

            for current_vessel in self._fleet:
                current_schedule = schedules.get(
                    current_vessel, current_vessel.schedule
                )
                new_schedule = current_schedule.copy()

                # Calculate cost and feasibility
                distance_to_pickup = self.headquarters.get_network_distance(
                    current_vessel.location, current_trade.origin_port
                )
                travel_time_to_pickup = current_vessel.get_travel_time(
                    distance_to_pickup
                )
                loading_time = current_vessel.get_loading_time(
                    current_trade.cargo_type, current_trade.amount
                )
                total_travel_time = travel_time_to_pickup + loading_time

                # Verify time window
                if (
                    total_travel_time
                    > current_trade.time_window[1] - current_trade.time_window[0]
                ):
                    continue

                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    cost = self.calculate_cost(current_vessel, current_trade)

                    # Scoring based on multiple factors
                    score = (
                        current_trade.amount / (cost + 1e-6)  # Higher profitability
                        - total_travel_time * 0.1  # Penalize longer travel times
                        + current_vessel.capacity(current_trade.cargo_type)
                        * 0.01  # Reward larger capacity
                    )

                    if score > best_score:
                        best_score = score
                        best_vessel = current_vessel
                        best_schedule = new_schedule

            # Assign trade to the best vessel
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
            else:
                unassigned_trades.append(current_trade)

        # Step 3: Attempt to reassign unassigned trades
        for trade in unassigned_trades[:]:
            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()

                distance_to_pickup = self.headquarters.get_network_distance(
                    vessel.location, trade.origin_port
                )
                travel_time_to_pickup = vessel.get_travel_time(distance_to_pickup)
                loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)

                # Check time window again
                if (
                    travel_time_to_pickup + loading_time
                    > trade.time_window[1] - trade.time_window[0]
                ):
                    continue

                new_schedule.add_transportation(trade)
                if new_schedule.verify_schedule():
                    schedules[vessel] = new_schedule
                    scheduled_trades.append(trade)
                    unassigned_trades.remove(trade)
                    break

        # Step 4: Log unassigned trades
        if unassigned_trades:
            print(
                f"Unassigned trades: {[trade.origin_port.name + ' -> ' + trade.destination_port.name for trade in unassigned_trades]}"
            )

        # Step 5: Return the proposed schedules
        costs = {
            trade: self.calculate_cost(vessel, trade)
            for trade in scheduled_trades
            for vessel in schedules.keys()
        }
        return ScheduleProposal(schedules, scheduled_trades, costs)

    def assign_schedules(self, trades):
        """
        Find schedules for a list of trades by assigning them to vessels in the fleet. Scheduling phase.

        :param trades: List of trades (contracts) to schedule.
        :return: ScheduleProposal containing schedules, scheduled trades, and costs.
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []
        full_cost = []

        # Step 1: Sort trades by priority (e.g., profit margin and earliest pickup time)
        # trades = sorted(trades, key=lambda t: (t.amount / self.calculate_cost(vessel, t), -t.earliest_pickup), reverse=True)

        # Step 2: Iterate over each trade and try to assign to the best vessel
        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            best_score = float("-inf")
            best_cost = float("inf")

            # Step 3: Try to assign the trade to each vessel and calculate the cost
            for current_vessel in self._fleet:
                current_vessel_schedule = schedules.get(
                    current_vessel, current_vessel.schedule
                )
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)

                if new_schedule.verify_schedule():
                    # Calculate the cost of this schedule
                    cost = self.calculate_cost(current_vessel, current_trade)
                    if cost < best_cost:
                        best_cost = cost
                        best_vessel = current_vessel
                        best_schedule = new_schedule

            # Step 4: Assign the trade to the best vessel if found
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
                full_cost.append(best_cost)  # Record the minimum cost
            else:
                # If no suitable vessel is found, record the trade as unassigned
                unassigned_trades.append(current_trade)

        # Step 5: Log unassigned trades for debugging
        if unassigned_trades:
            print(
                f"Unassigned trades: {[trade.origin_port.name + ' -> ' + trade.destination_port.name for trade in unassigned_trades]}"
            )

        # Step 6: Return the scheduling proposal
        return ScheduleProposal(schedules, scheduled_trades, full_cost)

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

    def create_bid(self, trade, cost_estimate):
        # 1. Base margin
        base_margin = 0.2  # 20%

        # 2. Adjust if your vessels are already busy
        fleet_utilization = self.estimate_fleet_utilization()
        if fleet_utilization > 0.8:
            base_margin += 0.3  # push up to 50% margin if you're busy
        elif fleet_utilization < 0.2:
            base_margin -= 0.05 # you can bid more aggressively

        # 3. Adjust if competitor is far away (big advantage => higher margin)
        competitor_distance = self.find_closest_competitor_distance(trade)
        your_distance = self.estimate_distance_to_trade(trade)
        if competitor_distance - your_distance > 500:  # means competitor is far
            base_margin += 0.1

        # 4. Final check or clamp
        final_margin = max(0.1, min(base_margin, 1.0))  # clamp between 10% and 100%

        return cost_estimate * (1 + final_margin)

    def propose_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []
        costs = {}

        # Sort trades
        trades = sorted(
            trades,
            key=lambda t: (
                t.amount / max(1, t.time_window[1] - t.time_window[0]),
                -t.earliest_pickup,
            ),
            reverse=True,
        )

        # For each trade, try to find the best (vessel + insertion point)
        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            best_score = float("-inf")
            best_cost = float("inf")

            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)

                # Check all possible insertion points
                insertion_points = current_schedule.get_insertion_points(current_trade)
                for pickup_idx, dropoff_idx in insertion_points:
                    trial_schedule = current_schedule.copy()
                    trial_schedule.add_transportation(
                        trade=current_trade,
                        pickup_location=pickup_idx,
                        dropoff_location=dropoff_idx,
                    )

                    # Verify feasibility
                    if trial_schedule.verify_schedule():
                        cost = self.calculate_cost(vessel, current_trade)
                        score = self.compute_score(
                            vessel=vessel,
                            trade=current_trade,
                            cost=cost,
                            schedule=trial_schedule,
                        )

                        # Update best if it beats our current best_score
                        if score > best_score:
                            best_score = score
                            best_vessel = vessel
                            best_schedule = trial_schedule
                            best_cost = cost

            # After checking all vessels & insertion points, record the best assignment
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
                costs[current_trade] = best_cost
            else:
                unassigned_trades.append(current_trade)

        return ScheduleProposal(schedules, scheduled_trades, unassigned_trades, costs)
