from mable.cargo_bidding import TradingCompany
from mable.examples import environment, fleets, shipping, companies


class MyCompany(TradingCompany):

    def inform(self, trades, *args, **kwargs):
        return []

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        competitor_name = "Arch Enemy Ltd."
        competitor_won_contracts = auction_ledger[competitor_name]
        competitor_fleet = [c for c in self.headquarters.get_companies() if c.name == competitor_name].pop().fleet
        # TODO find and print predicted bid factors

    def predict_cost(self, vessel, trade):
        total_cost = 1  # TODO Replace
        return total_cost


def build_specification():
    specifications_builder = environment.get_specification_builder(fixed_trades=shipping.example_trades_1())
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(MyCompany.Data(MyCompany, fleet, MyCompany.__name__))
    specifications_builder.add_company(
        companies.MyArchEnemy.Data(companies.MyArchEnemy, fleets.example_fleet_2(), "Arch Enemy Ltd."))
    sim = environment.generate_simulation(
        specifications_builder,
        show_detailed_auction_outcome=True)
    sim.run()


if __name__ == '__main__':
    build_specification()
