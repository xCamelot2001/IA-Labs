from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets, companies
from typing import Dict, List, Tuple
import statistics

class CompanyAnalyzer(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self.competitor_data: Dict[str, List[Tuple[float, float]]] = {}  # company -> [(bid, cost)]

    def predict_cost(self, vessel, trade):
        """Calculate base cost for a vessel to complete a trade"""
        # Calculate loading/unloading times
        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        unloading_time = loading_time  # Assuming symmetric loading/unloading

        # Get distances and travel time
        travel_distance = self.headquarters.get_network_distance(
            trade.origin_port, trade.destination_port)
        travel_time = vessel.get_travel_time(travel_distance)

        # Calculate costs
        loading_cost = vessel.get_loading_consumption(loading_time)
        unloading_cost = vessel.get_unloading_consumption(unloading_time)
        travel_cost = vessel.get_laden_consumption(travel_time, vessel.speed)

        total_cost = loading_cost + unloading_cost + travel_cost
        return total_cost

    def inform(self, trades, *args, **kwargs):
        """Don't bid, just observe"""
        return []

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """Analyze auction results to predict competitor profit factors"""
        if not auction_ledger:
            return

        # Focus on Arch Enemy Ltd
        competitor_name = "Arch Enemy Ltd."
        
        try:
            competitor = [c for c in self.headquarters.get_companies() 
                         if c.name == competitor_name][0]
        except IndexError:
            print(f"Competitor {competitor_name} not found")
            return

        # Get their won contracts
        won_contracts = auction_ledger.get(competitor_name, [])
        
        # For each won contract
        for contract in won_contracts:
            trade = contract.trade
            winning_bid = contract.price
            
            # Find their closest vessel that could have done this trade
            closest_vessel = min(competitor.fleet,
                key=lambda v: self.headquarters.get_network_distance(
                    v.location, trade.origin_port))
            
            # Calculate what we think their base cost was
            predicted_cost = self.predict_cost(closest_vessel, trade)
            
            # Store the bid/cost pair
            if competitor_name not in self.competitor_data:
                self.competitor_data[competitor_name] = []
            self.competitor_data[competitor_name].append((winning_bid, predicted_cost))

            # Calculate and print the profit factor
            profit_factor = winning_bid / predicted_cost
            
            # Get number of companies that could have bid
            potential_bidders = len([c for c in self.headquarters.get_companies()
                if any(self.predict_cost(v, trade) <= trade.profit 
                    for v in c.fleet)])
            
            print(f"\nTrade Analysis for {competitor_name}:")
            print(f"Winning bid: {winning_bid:.2f}")
            print(f"Predicted cost: {predicted_cost:.2f}")
            print(f"Implied profit factor: {profit_factor:.2f}")
            print(f"Number of potential bidders: {potential_bidders}")
            
            # Calculate average profit factor across all observations
            if self.competitor_data[competitor_name]:
                avg_factor = statistics.mean(
                    bid/cost for bid, cost in self.competitor_data[competitor_name])
                print(f"Average profit factor to date: {avg_factor:.2f}")

def build_specification():
    specifications_builder = environment.get_specification_builder(
        trades_per_occurrence=5,
        num_auctions=12)
    
    # Add our analyzer company
    my_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(
        CompanyAnalyzer.Data(CompanyAnalyzer, my_fleet, "Analyzer"))

    # Add competitors
    arch_enemy_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(
        companies.MyArchEnemy.Data(
            companies.MyArchEnemy, 
            arch_enemy_fleet,
            "Arch Enemy Ltd.",
            profit_factor=1.5))

    sim = environment.generate_simulation(
        specifications_builder,
        show_detailed_auction_outcome=True,
        global_agent_timeout=60)
    sim.run()

if __name__ == '__main__':
    build_specification()