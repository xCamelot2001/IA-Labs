"""
A module to support the collection of metrics for a simulation.
"""

from mable.simulation_environment import SimulationEngineAware
from mable.util import JsonAble

FUEL_CONSUMPTION_KEY = "fuel_consumption"
CO2_EMISSIONS_KEY = "co2_emissions"
FUEL_COST_KEY = "fuel_cost"
VESSEL_ROUTE_KEY = "route"


class VesselKey(JsonAble):
    """
    A vessel key that is the compound of the id of a company and an id for the vessel.
    """

    def __init__(self, company_id, vessel_id):
        """
        Constructor.
        :param company_id: int
            The id of the company the vessel belongs to.
        :param vessel_id: int
            The id of the vessel.
        """
        super().__init__()
        self._company_id = company_id
        self._vessel_id = vessel_id

    @property
    def company_id(self):
        return self._company_id

    @property
    def vessel_id(self):
        return self._vessel_id

    @property
    def key_tuple(self):
        """
        :return: (int, int)
            The tuple of the company id and the vessel id (in this order).
        """
        return self._company_id, self._vessel_id

    def __repr__(self):
        return str(self.key_tuple)

    def __hash__(self):
        return hash(self.key_tuple)

    def __eq__(self, other):
        """
        Two VesselKeys are equal if their company id and vessel id are the same. A VesselKey is equal to a
        tuple if the tuple contains the same company id and vessel id.
        :param other:
        :return:
        """
        are_equal = False
        if isinstance(other, VesselKey):
            if self._company_id == other.company_id and self._vessel_id == other.vessel_id:
                are_equal = True
        elif isinstance(other, tuple) and len(other) == 2:
            if self._company_id == other[0] and self._vessel_id == other[1]:
                are_equal = True
        return are_equal


class MetricDict(dict):
    """
    A dict that works with VesselKeys by transforming them into string representations of the tuples
    (see :py:func:`VesselKey.key_tuple`).
    """

    def __setitem__(self, key, value):
        if isinstance(key, VesselKey):
            key = str(key)
        super().__setitem__(key, value)

    def __getitem__(self, key):
        if isinstance(key, VesselKey):
            key = str(key)
        return super().__getitem__(key)


class MetricsCollector(JsonAble, SimulationEngineAware):
    """
    An object to collect company level and vessel level metrics. Each vessel and company can have collections
    of metrics via specifiable keys.
    """

    def __init__(self):
        super().__init__()
        self._last_company_id = -1
        self._last_vessel_ids = {}
        self._company_ids = {}
        self._vessel_ids = {}
        self._company_names = {}
        self._company_metrics = MetricDict()
        self._vessel_metrics = MetricDict()
        self._global_metrics = MetricDict()

    def _get_next_company_id(self, company):
        """
        Assign the next id to the specified company. The association is remembered.
        :param company:
            The company
        :return: int
            The id of the company.
        """
        self._last_company_id += 1
        self._company_ids[company] = self._last_company_id
        self._last_vessel_ids[self._last_company_id] = -1
        self._company_metrics[self._last_company_id] = {}
        return self._last_company_id

    def _get_next_vessel_id(self, company, vessel):
        """
        Assign the next id to the specified vessel for the specified company. The association is remembered.
        :param company:
            The company
        :param vessel:
            The vessel.
        :return: VesselKey
            The key of the vessel.
        """
        try:
            company_id = self._company_ids[company]
        except KeyError:
            company_id = self._get_next_company_id(company)
        self._last_vessel_ids[company_id] += 1
        current_vessel_id = VesselKey(company_id, self._last_vessel_ids[company_id])
        self._vessel_ids[vessel] = current_vessel_id
        self._vessel_metrics[current_vessel_id] = {}
        return current_vessel_id

    def get_company_id(self, company, create_id_if_not_exists=True):
        """
        Get the id of the specified company. If create_id_if_not_exists exists (default) a new key is created
        if no id for the specified company is known.
        :param company:
            The company.
        :param create_id_if_not_exists: bool
            Indicated if a new id should be created if non exists.
        :return: int
            The id of the company.
        :raises KeyError:
            If no id for the specified company is known and create_id_if_not_exists is False.
        """
        try:
            company_id = self._company_ids[company]
        except KeyError as key_error:
            if create_id_if_not_exists:
                company_id = self._get_next_company_id(company)
            else:
                raise key_error
        return company_id

    def get_vessel_id(self, vessel, company=None, create_both_ids_if_not_exists=True):
        """
        Get the key of the specified vessel. If create_id_if_not_exists exists (default) a new key is created
        if no id for the specified vessel is known. This extends to the company if the company is not yet known.
        If new keys are generated and the company is not specified, i.e. parameter is set to None, an attempt
        is made to determine the company based on all shipping company's fleets.
        :param vessel:
            The vessel.
        :param company:
            The company.
        :param create_both_ids_if_not_exists: bool
            Indicated if new ids should be created if non exists.
        :return: VesselKey
            The key of the company.
        :raises KeyError:
            If no key for the specified vessel is known and create_id_if_not_exists is False.
        :raises ValueError:
            If new keys are supposed to be generated but the company is not specified nor could a company be
            determined.
        """
        try:
            vessel_id = self._vessel_ids[vessel]
        except KeyError as key_error:
            if create_both_ids_if_not_exists:
                if company is None:
                    shipping_companies = self._engine.shipping_companies
                    try:
                        company = next((c for c in shipping_companies if vessel in c.fleet))
                    except StopIteration:
                        raise ValueError("neither company specified nor company knows for vessel.")
                vessel_id = self._get_next_vessel_id(company, vessel)
                self._company_names[self._company_ids.get(company)] = company.name
            else:
                raise key_error
        return vessel_id

    def _add_company_numeric_metric(self, company_id, key, value):
        if key not in self._company_metrics[company_id]:
            self._company_metrics[company_id][key] = 0
        self._company_metrics[company_id][key] += value

    def add_company_numeric_metric(self, company, key, value):
        """
        Add a numeric metric for a company. The value is added to the value in the
        collections of metrics for the specified company under the specified key.
        If it is the first time the metric is added it is initialised as zero before adding the value.
        :param company:
            The company
        :param key:
            The key.
        :param value:
            The value. Anything that specifies __iadd__ or __add__.
        """
        company_id = self.get_company_id(company)
        self._add_company_numeric_metric(company_id, key, value)

    def add_dual_numeric_metric(self, vessel, key, value):
        """
        Add a numeric metric for a vessel and its company. The value is added to the value in the
        collections of metrics for the specified vessel and the vessel's company under the specified key.
        If it is the first time the metric is added it is initialised as zero before adding the value.
        :param vessel:
            The vessel
        :param key:
            The key.
        :param value:
            The value. Anything that specifies __iadd__ or __add__.
        """
        vessel_id = self.get_vessel_id(vessel)
        company_id = vessel_id.company_id
        self._add_company_numeric_metric(company_id, key, value)
        if key not in self._vessel_metrics[vessel_id]:
            self._vessel_metrics[vessel_id][key] = 0
        self._vessel_metrics[vessel_id][key] += value

    def add_global_company_list_metric(self, key, value):
        """
        Add a global list metric.
        :param key:
            The key.
        :param value:
            The value.
        """
        if key not in self._global_metrics:
            self._global_metrics[key] = []
        self._global_metrics[key].append(value)

    def to_json(self):
        """
        A dict of the company and the vessel metrics.
        :return: dict
            {"company_metrics": <companies' metrics>, "vessel_metrics": <vessels' metrics>}
        """
        return {
            "company_names": self._company_names,
            "company_metrics": self._company_metrics,
            "vessel_metrics": self._vessel_metrics,
            "global_metrics": self._global_metrics
        }


class GlobalMetricsCollector(MetricsCollector):
    """
    A metrics collector that collects metrics for the entire operational space.
    """

    def add_fuel_consumption(self, vessel, consumption):
        """
        TODO finish when clear how consumption is computed
        :param vessel:
        :param consumption:
        :return:
        """
        self.add_dual_numeric_metric(vessel, FUEL_CONSUMPTION_KEY, consumption)

    def add_co2_emissions(self, vessel, emissions):
        """
        TODO
        :param vessel:
        :param emissions:
        :return:
        """
        self.add_dual_numeric_metric(vessel, CO2_EMISSIONS_KEY, emissions)

    def add_cost(self, vessel, cost):
        """
        TODO
        :param vessel:
        :param cost:
        :return:
        """
        self.add_dual_numeric_metric(vessel, FUEL_COST_KEY, cost)

    def add_route_point(self, location, vessel):
        vessel_id = self.get_vessel_id(vessel)
        if VESSEL_ROUTE_KEY not in self._vessel_metrics[vessel_id]:
            self._vessel_metrics[vessel_id][VESSEL_ROUTE_KEY] = []
        self._vessel_metrics[vessel_id][VESSEL_ROUTE_KEY].append(location)


class RegionalMetricsCollector(MetricsCollector):
    """
    A metrics collector that collects metrics for subdivision of the operational space.
    """

    def add_fuel_consumption(self, vessel, consumption, region):
        self.add_dual_numeric_metric(vessel, (region, FUEL_CONSUMPTION_KEY), consumption)
