"""
Safe distribution of information to companies.
"""
import copy
from typing import TYPE_CHECKING, Dict, List

from mable.shipping_market import Contract

if TYPE_CHECKING:
    from mable.engine import SimulationEngine
    from mable.simulation_space.universe import OnJourney, Location
    from mable.transport_operation import Vessel, ShippingCompany
    from mable.shipping_market import AuctionAllocationResult, Trade


class CompanyHeadquarters:
    """
    A centre that allows the trading companies to interact with the wider environment.
    """

    def __init__(self, simulation_engine):
        """
        :param simulation_engine: The simulation engine.
        :type simulation_engine: SimulationEngine
        """
        super().__init__()
        self._engine = simulation_engine
        self._sanitised_shipping_companies = None
        self._shipping_companies_update_time = None

    @property
    def current_time(self):
        """
        The current time of the simulation.

        :return: The current time.
        :rtype: float
        """
        return self._engine.world.current_time

    def _apply_schedules(self, company, schedules):
        # TODO check that only vessels of the company are being used
        # TODO verify schedules
        pass

    def get_network_port_or_default(self, port_name, default):
        """
        Returns a port by name or the default value in case no port with the specified name exists.

        :param port_name: The name of the port.
        :type port_name: str
        :param default: The default value to return. By default, this is None.
        :type default: Any
        :return: Either the port or whatever is passed to default (None by default).
        :rtype: Union[Port, Any]
        """
        return self._engine.world.network.get_port_or_default(port_name, default)

    def get_network_distance(self, location_one, location_two):
        """
        Get the distance between two locations.

        If there is no route between the two locations infinity (math.inf) if returned.

        **Warning**: *If one or both of the locations come from a vessel on a journey, the calculation will take time.* \
        *It may be better to work with the origin and destination of a journey rather than the actual location of the* \
        *vessel.*

        :param location_one: The first location.
        :type location_one: Union[Port, str]
        :param location_two: The second location.
        :type location_one: Union[Port, str]
        :return: The distance or math.inf if no route between the two locations exists.
        :rtype: float
        """
        return self._engine.world.network.get_distance(location_one, location_two)

    def get_journey_location(self, journey, vessel, time=None):
        """
        Get the current location of a vessel on a journey.

        **Warning**: *If the location is intended to calculate an exact distance with*
        :py:func:`get_network_distance`, \
        *that calculation will take time.* \
        *It may be better to work with the origin and destination of a journey rather than the actual location of the* \
        *vessel.*

        :param journey: The journey.
        :type journey: OnJourney
        :param vessel: The vessel that is performing the journey.
        :type vessel: Vessel
        :param time: The time at which the journey location will be calculated. Default, i.e. None, is the current time.
        :type time: float
        :return: The current location the vessel is in.
        :rtype: Location
        """
        if time is None:
            time = self.current_time
        current_location = self._engine.world.network.get_journey_location(journey, vessel, time)
        return current_location

    def get_companies(self):
        """
        Get all companies.
        :return:
        """
        if (self._sanitised_shipping_companies is None
                or (self._shipping_companies_update_time is not None
                    and self._shipping_companies_update_time < self.current_time)):
            sanitised_shipping_companies = []
            for one_company in self._engine.shipping_companies:
                one_company_dummy_fleet = []
                for one_vessel in one_company.fleet:
                    capacities_and_loading_rates = one_vessel.capacities_and_loading_rates
                    location = one_vessel.location
                    speed = one_vessel.speed
                    propelling_engine = copy.deepcopy(one_vessel.propelling_engine)
                    one_vessel_dummy = type(one_vessel)(
                        capacities_and_loading_rates, location, speed, propelling_engine,
                        name=one_vessel.name)
                    one_vessel_dummy.schedule.set_engine(self._engine)
                    one_company_dummy_fleet.append(one_vessel_dummy)
                one_company_dummy = type(one_company)(one_company_dummy_fleet, one_company.name)
                one_company_dummy.pre_inform = None
                one_company_dummy.inform = None
                one_company_dummy.receive = None
                sanitised_shipping_companies.append(one_company_dummy)
            self._sanitised_shipping_companies = sanitised_shipping_companies
            self._shipping_companies_update_time = self.current_time
        return self._sanitised_shipping_companies


class MarketAuthority:

    def __init__(self):
        self._contracts_per_company: Dict[ShippingCompany, List[Contract]] = {}

    @property
    def contracts_per_company(self):
        return self._contracts_per_company

    def trade_fulfilled(self, trade, company):
        """
        :param trade: The trade.
        :type trade: Trade
        :param company: The company fulfilling the trade.
        :type company: ShippingCompany
        """
        contract_for_trade = next(c for c in self._contracts_per_company[company] if c.trade == trade)
        contract_for_trade.fulfilled = True

    def add_allocation_results(self, allocation_results):
        """
        :param allocation_results:
        :type allocation_results: AuctionAllocationResult
        """
        for one_company in allocation_results.ledger.keys():
            if not one_company in self._contracts_per_company:
                self._contracts_per_company[one_company] = []
            self._contracts_per_company[one_company].extend(allocation_results.ledger[one_company])
