from mable.cargo_bidding import TradingCompany
from mable.examples import environment, fleets, shipping, companies
from mable.transport_operation import ScheduleProposal


class MyCompany(TradingCompany):

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        trades = [one_contract.trade for one_contract in contracts]
        scheduling_proposal = self.find_schedules(trades)
        _ = self.apply_schedules(scheduling_proposal.schedules)

    def propose_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            competing_vessels = self.find_competing_vessels(current_trade)
            if len(competing_vessels) == 0:
                print(f"{current_trade.origin_port.name.split('-')[0]}"
                      f" -> {current_trade.destination_port.name.split('-')[0]}: No competing vessels found")
            for one_company in competing_vessels:
                distance = self.headquarters.get_network_distance(
                          competing_vessels[one_company].location, current_trade.origin_port)
                print(f"{current_trade.origin_port.name.split('-')[0]}"
                      f" -> {current_trade.destination_port.name.split('-')[0]}:"
                      f" {one_company.name}'s {competing_vessels[one_company].name}"
                      f" in {competing_vessels[one_company].location.name.split('-')[0]}"
                      f" at {distance} NM")
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self._fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    schedules[current_vessel] = new_schedule
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, {})

    def find_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self._fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    schedules[current_vessel] = new_schedule
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, {})

    def predict_cost(self, vessel, trade):
        total_cost = 0
        return total_cost

    def find_competing_vessels(self, trade):
        competing_vessels = {}
        # TODO add competing vessels
        # competing_vessels[<a company>] = <a vessel>
        return competing_vessels


def build_specification():
    specifications_builder = environment.get_specification_builder(fixed_trades=shipping.example_trades_1())
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(MyCompany.Data(MyCompany, fleet, MyCompany.__name__))
    specifications_builder.add_company(
        companies.PondPlayer.Data(companies.PondPlayer, fleets.example_fleet_3(), companies.PondPlayer.__name__))
    sim = environment.generate_simulation(
        specifications_builder,
        show_detailed_auction_outcome=True)
    sim.run()


if __name__ == '__main__':
    build_specification()
