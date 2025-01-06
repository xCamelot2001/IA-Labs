from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade
from mable.extensions.fuel_emissions import VesselWithEngine
import traceback

##############################################################################
# 1) HELPER FUNCTIONS
##############################################################################

def travel_cost(headquarters, portA, portB, current_time, vessel):
    """
    Return the cost to travel from portA -> portB if starting at current_time.
    Basic approach: distance * some fuel cost. You can improve as needed.
    """
    distance = headquarters.get_network_distance(portA, portB)
    travel_time = vessel.get_travel_time(distance)
    # Placeholder for cost-of-fuel logic
    cost_of_fuel_per_hr = 10.0
    cost_here = travel_time * cost_of_fuel_per_hr
    return cost_here

def idle_cost(current_time, pickup_time):
    """
    Cost of idling until pickup_time if the vessel arrives early.
    """
    wait_duration = max(0, pickup_time - current_time)
    idle_rate_per_hr = 2.0
    return wait_duration * idle_rate_per_hr

def compute_bid(headquarters, trade, vessel, vessel_state, company):
    """
    Return a recommended bid for the given trade & vessel, factoring in cost & margin,
    plus competitor data and optional urgency premium.
    """
    (current_port, current_time) = vessel_state[vessel]
    (earliest_pickup, latest_pickup, earliest_dropoff, latest_dropoff) = trade.time_window

    # 1) Baseline cost: reposition + idle + main travel
    cost_to_pickup = travel_cost(headquarters, current_port, trade.origin_port, current_time, vessel)
    # If you prefer to idle only after repositioning, you can adjust accordingly
    idle_c = idle_cost(current_time, earliest_pickup or current_time)
    cost_to_dropoff = travel_cost(headquarters, trade.origin_port, trade.destination_port, 
                                  max(current_time, earliest_pickup or current_time),
                                  vessel)
    total_cost = cost_to_pickup + idle_c + cost_to_dropoff

    # 2) Competitor-aware markup
    #    If we have competitor data (how much they tend to bid above our cost), use it
    if company.competitor_markup_estimates:
        avg_factor = sum(company.competitor_markup_estimates) / len(company.competitor_markup_estimates)
        # Undercut slightly by 5% or you can choose any factor
        margin_amount = total_cost * (avg_factor * 0.95)
    else:
        # Fallback if no data
        margin_rate = 0.2  # default to 20%
        margin_amount = total_cost * margin_rate

    # Ensure a floor margin so we don't bid too low
    min_margin_rate = 0.05  # 5%
    margin_amount = max(margin_amount, total_cost * min_margin_rate)

    # 3) (Optional) Urgency premium if the pickup window is tight
    pickup_window = (latest_pickup or earliest_pickup) - (earliest_pickup or 0)
    # If the pickup window is small (e.g., < 72 hours), charge extra
    if pickup_window and pickup_window < 72:
        urgency_factor = 1.15  # e.g. +15%
        margin_amount *= urgency_factor

    # 4) Final bid price
    bid_price = total_cost + margin_amount
    return bid_price


##############################################################################
# 2) THE AGENT
##############################################################################

class Company5(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None

        self._distances = {}
        self.saved_estimated_costs = {}
        self.competitor_data = {}
        # Keep track of competitor markup data here
        self.competitor_markup_estimates = []

        # Vessel state: (current_port, earliest_free_time)
        self.vessel_state = {v: (v.location, 0.0) for v in self._fleet}


    # ----------------------------------------------------------------------
    # 1) PRE-INFORM
    # ----------------------------------------------------------------------
    def pre_inform(self, trades, time):
        self._future_trades = trades
        self._future_auction_time = time
        print(f"[pre_inform] Future trades at time {time}: {trades}")

    # ----------------------------------------------------------------------
    # 2) INFORM -> propose schedules & create bids
    # ----------------------------------------------------------------------
    def inform(self, trades, *args, **kwargs):
        print(f"[inform] Vessel state: {self.vessel_state}")
        print(f"[inform] Current trades: {trades}")
        try:
            proposed_scheduling = self.propose_schedules(trades)
            scheduled_trades = proposed_scheduling.scheduled_trades

            bids = []
            for trade in scheduled_trades:
                # Store a cost estimate for future analysis
                cost_estimate = proposed_scheduling.costs.get(trade, 0.0)
                self.saved_estimated_costs[trade] = cost_estimate

                # Find which vessel we assigned
                best_vessel = None
                for v, sched in proposed_scheduling.schedules.items():
                    if trade in sched.scheduled_trades:
                        best_vessel = v
                        break
                if best_vessel is None:
                    continue

                # Use the improved dynamic competitor margin in compute_bid
                recommended_bid = compute_bid(
                    self.headquarters, 
                    trade, 
                    best_vessel, 
                    self.vessel_state,
                    self  # pass the company so we can use competitor data
                )

                if recommended_bid <= 0.1:
                    continue

                print(f"[inform] Bidding for {trade} with recommended_bid={recommended_bid}")
                bids.append(Bid(amount=recommended_bid, trade=trade))

            return bids
        except Exception as e:
            print(f"[inform] Error: {e}")
            traceback.print_exc()
            return []

    # ----------------------------------------------------------------------
    # 3) RECEIVE -> finalize which trades we actually won
    # ----------------------------------------------------------------------
    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        print(f"[receive] Auction ledger: {auction_ledger}")
        print(f"[receive] Contracts: {contracts}")
        try:
            if auction_ledger:
                for c_name, w_trades in auction_ledger.items():
                    print(f"[receive] {c_name} won trades: {w_trades}")
                    # Learn competitor markups for trades we did NOT win
                    for trade_info in w_trades:
                        trade_obj = trade_info.trade
                        # Extract the final price from the correct attribute
                        final_price = getattr(trade_info, 'payment', None)
                        if final_price is None:
                            print(f"[receive] Warning: No payment found for trade {trade_obj}")
                            continue
                        self.learn_competitor_markup(trade_obj, final_price)

            # The trades we actually got
            trades_we_won = [c.trade for c in contracts]
            final_scheduling = self.assign_schedules(trades_we_won)
            # Mark them
            for c in contracts:
                if c.trade in final_scheduling.scheduled_trades:
                    c.fulfilled = True

            self.current_schedule = contracts
            self._future_trades = None

        except Exception as e:
            print(f"[receive] Error: {e}")
            import traceback
            traceback.print_exc()
    # ----------------------------------------------------------------------
    # 4) PROPOSE_SCHEDULES
    # ----------------------------------------------------------------------
    def propose_schedules(self, trades):
        """
        1. Filter out infeasible trades
        2. Sort trades by a more profit or time-window oriented heuristic
        3. For each feasible trade, pick the best vessel
        """
        schedules = {}
        scheduled_trades = []
        costs = {}

        # Example: sort trades by (cargo amount) and then smaller pickup windows first
        trades = sorted(
            trades,
            key=lambda t: (
                t.amount,
                -((t.time_window[1] or t.time_window[0]) - (t.time_window[0] or 0))  # shorter window has higher priority
            ),
            reverse=True
        )

        for trade in trades:
            best_vessel = None
            best_cost = float('inf')

            for vessel in self._fleet:
                if not self.is_feasible_in_time(vessel, trade):
                    continue

                cost_val = self.calculate_total_cost_with_positioning(vessel, trade)

                if cost_val < best_cost:
                    best_cost = cost_val
                    best_vessel = vessel

            if best_vessel:
                # Attempt to add to that vessel's schedule
                current_schedule = schedules.get(best_vessel, best_vessel.schedule)
                new_schedule = current_schedule.copy()
                new_schedule.add_transportation(trade)

                if new_schedule.verify_schedule():
                    schedules[best_vessel] = new_schedule
                    scheduled_trades.append(trade)
                    costs[trade] = best_cost
            else:
                # If no vessel can handle it feasibly, skip
                pass

        return ScheduleProposal(schedules, scheduled_trades, costs)

    # ----------------------------------------------------------------------
    # 5) ASSIGN_SCHEDULES
    # ----------------------------------------------------------------------
    def assign_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        costs = {}

        for trade in trades:
            best_vessel = None
            best_cost = float('inf')
            best_schedule = None

            for vessel in self._fleet:
                if not self.is_feasible_in_time(vessel, trade):
                    continue

                base_schedule = schedules.get(vessel, vessel.schedule)
                trial_sched = base_schedule.copy()
                trial_sched.add_transportation(trade)

                if trial_sched.verify_schedule():
                    cost_val = self.calculate_total_cost_with_positioning(vessel, trade)
                    if cost_val < best_cost:
                        best_cost = cost_val
                        best_vessel = vessel
                        best_schedule = trial_sched

            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(trade)
                costs[trade] = best_cost
            else:
                print(f"[assign_schedules] Could not schedule trade: {trade}")

        return ScheduleProposal(schedules, scheduled_trades, costs)

    # ----------------------------------------------------------------------
    # 6) TIME FEASIBILITY
    # ----------------------------------------------------------------------
    def is_feasible_in_time(self, vessel, trade):
        earliest_pickup = trade.time_window[0] or 0
        latest_pickup = trade.time_window[1] or 999999
        earliest_drop_off = trade.time_window[2] or 0
        latest_drop_off = trade.time_window[3] or 999999

        current_port, vessel_free_time = self.vessel_state.get(vessel, (None, None))

        # Validate current_port and trade.origin_port
        if current_port is None:
            print(f"[is_feasible_in_time] Error: Vessel {vessel} has no current port.")
            return False
        if trade.origin_port is None:
            print(f"[is_feasible_in_time] Error: Trade {trade} has no origin port.")
            return False

        # Calculate distance to origin
        try:
            distance_to_origin = self.headquarters.get_network_distance(current_port, trade.origin_port)
        except KeyError as e:
            print(f"[is_feasible_in_time] Error: Invalid port in distance calculation. {e}")
            return False

        reposition_travel_time = vessel.get_travel_time(distance_to_origin)
        arrival_time_at_origin = vessel_free_time + reposition_travel_time
        if arrival_time_at_origin > latest_pickup:
            return False

        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        depart_time_from_origin = arrival_time_at_origin + loading_time

        distance_o_d = self.headquarters.get_network_distance(trade.origin_port, trade.destination_port)
        travel_time = vessel.get_travel_time(distance_o_d)
        arrival_time_at_destination = depart_time_from_origin + travel_time
        if arrival_time_at_destination > latest_drop_off:
            return False

        return True

    # ----------------------------------------------------------------------
    # 7) COST WITH POSITIONING
    # ----------------------------------------------------------------------
    def calculate_total_cost_with_positioning(self, vessel, trade):
        vessel_port, vessel_time = self.vessel_state[vessel]

        # Reposition
        dist_key = (vessel_port, trade.origin_port)
        if dist_key not in self._distances:
            net_dist = self.headquarters.get_network_distance(vessel_port, trade.origin_port)
            self._distances[dist_key] = net_dist
        reposition_dist = self._distances[dist_key]
        reposition_time = vessel.get_travel_time(reposition_dist)
        reposition_cost = vessel.get_cost(vessel.get_ballast_consumption(reposition_time, vessel.speed))

        # Loading
        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        loading_cost = vessel.get_cost(vessel.get_loading_consumption(loading_time))

        # Main travel (laden)
        dist_key2 = (trade.origin_port, trade.destination_port)
        if dist_key2 not in self._distances:
            net_dist2 = self.headquarters.get_network_distance(*dist_key2)
            self._distances[dist_key2] = net_dist2
        distance = self._distances[dist_key2]
        travel_time = vessel.get_travel_time(distance)
        laden_cost = vessel.get_cost(vessel.get_laden_consumption(travel_time, vessel.speed))

        # Unloading
        unloading_time = loading_time
        unloading_cost = vessel.get_cost(vessel.get_unloading_consumption(unloading_time))

        total_cost = reposition_cost + loading_cost + laden_cost + unloading_cost
        return total_cost

    # ----------------------------------------------------------------------
    # 8) LEARN COMPETITOR
    # ----------------------------------------------------------------------
    def learn_competitor_markup(self, trade, final_price):
        """
        Compare competitor's winning price vs. your internal cost estimate
        to update competitor_markup_estimates.
        """
        cost_est = self.saved_estimated_costs.get(trade, None)
        if cost_est:
            competitor_factor = (final_price - cost_est) / cost_est
            # Save it for future margin decisions
            self.competitor_markup_estimates.append(competitor_factor)

    # ----------------------------------------------------------------------
    # 9) GUESS COMPETITOR PRICE (OPTIONAL)
    # ----------------------------------------------------------------------
    def guess_competitor_price(self, trade):
        """
        You could optionally implement a real guess for competitor price 
        based on competitor_markup_estimates, etc.
        """
        if self.competitor_markup_estimates:
            avg_factor = sum(self.competitor_markup_estimates) / len(self.competitor_markup_estimates)
            return self.saved_estimated_costs.get(trade, 0) * (1 + avg_factor)
        return float('inf')
