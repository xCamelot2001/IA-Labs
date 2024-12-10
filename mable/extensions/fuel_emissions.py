"""
Add fuel and emission capabilities.
"""
from typing import Dict, Any, List, TYPE_CHECKING

import attrs
from marshmallow import fields, post_load

from mable.simulation_de_serialisation import DynamicNestedField, DataClass, DataSchema
from mable.extensions.world_ports import WorldVessel
from mable.util import JsonAble
from mable.extensions import cargo_distributions
from mable import global_setup, instructions

if TYPE_CHECKING:
    from mable.transport_operation import CargoCapacity


FUEL_KEY = "fuels"


class FuelSpecsBuilder(instructions.Specifications.Builder):
    """
    Extends the specification builder to encode fuels.
    """

    def add_fuel(self, *args, **kwargs):
        if FUEL_KEY not in self._specifications:
            self._specifications[FUEL_KEY] = []
        fuel_dict = self._get_args_dict(*args, **kwargs)
        self._specifications[FUEL_KEY].append(fuel_dict)


class GlobalSetup:
    _global_setup: Dict[str, Any] = {}

    @classmethod
    def set_item(cls, key, value):
        cls._global_setup[key] = value

    @classmethod
    def get_item(cls, key):
        return cls._global_setup[key]

    @classmethod
    def get_keys(cls):
        return cls._global_setup.keys()


class FuelSimulationFactory(cargo_distributions.DistributionSimulationBuilder):
    """
    Extends the Simulation builder such that vessels have engines that use fuel for transportation.
    """
    # _global_setup: Dict[str, Any] | None = {}

    def __init__(self, class_factory, specifications):
        super().__init__(class_factory, specifications)
        GlobalSetup()
        self._fuels = None

    def generate_engine(self, *args, **kwargs):
        self.generate_fuels()
        return super().generate_engine(*args, **kwargs)

    def generate_fuels(self, *args, **kwargs):
        fuels_list = self._specifications[FUEL_KEY]
        self._fuels = []
        for one_fuel in fuels_list:
            one_fuel_instructions_args, _ = one_fuel[-1]
            one_fuel_instructions_args = one_fuel_instructions_args[0]
            self._fuels.append(self._class_factory.generate_fuel(**one_fuel_instructions_args))
        GlobalSetup.set_item(FUEL_KEY, self._fuels)
        global_setup.abc[FUEL_KEY] = self._fuels
        return self

    def generate_vessel(self, *args, **kwargs):
        kwargs["location"] = self._network.get_port_or_default(kwargs["location"], None)
        all_cargo_capacities = []
        for one_cargo_capacity in kwargs["capacities_and_loading_rates"]:
            all_cargo_capacities.append(self._class_factory.generate_cargo_capacity(**one_cargo_capacity))
        kwargs["capacities_and_loading_rates"] = all_cargo_capacities
        vessel_engine_args = kwargs["propelling_engine"]
        kwargs["propelling_engine"] = self.generate_vessel_engine(**vessel_engine_args)
        return self._class_factory.generate_vessel(**kwargs)

    def generate_vessel_engine(self, *args, **kwargs):
        fuel_name = kwargs["fuel"]
        fuel = next((f for f in self._fuels if f.name == fuel_name), None)
        kwargs["fuel"] = fuel
        kwargs["laden_consumption_rate"] = self.generate_consumption_rate(**kwargs["laden_consumption_rate"])
        kwargs["ballast_consumption_rate"] = self.generate_consumption_rate(**kwargs["ballast_consumption_rate"])
        return self._class_factory.generate_vessel_engine(**kwargs)

    def generate_consumption_rate(self, *args, **kwargs):
        return self._class_factory.generate_consumption_rate(**kwargs)


class FuelClassFactory(cargo_distributions.DistributionClassFactory):
    """
    Extends the class factory for the generation of vessels with engines that use different fuels.
    """

    @staticmethod
    def generate_vessel(*args, **kwargs):
        return VesselWithEngine(*args, **kwargs)

    @staticmethod
    def generate_vessel_engine(*args, **kwargs):
        return VesselEngine(*args, **kwargs)

    @staticmethod
    def generate_consumption_rate(*args, **kwargs):
        return ConsumptionRate(*args, **kwargs)

    @staticmethod
    def generate_fuel(*args, **kwargs):
        return Fuel(*args, **kwargs)


@attrs.define(kw_only=True)
class ConsumptionRate(JsonAble):
    """
    A polynomial consumption rate.

    The consumption for a specific speed over a specified time is:
    base * pow(speed, speed_power) * factor * time.
    """

    base: float
    speed_power: float
    factor: float

    def to_json(self):
        # noinspection PyTypeChecker
        # Trade is an attrs instance.
        return attrs.asdict(self)

    @attrs.define
    class Data(DataClass):
        base: float
        speed_power: float
        factor: float

        class Schema(DataSchema):
            base = fields.Float()
            speed_power = fields.Float()
            factor = fields.Float()


@attrs.define(kw_only=True)
class Fuel(JsonAble):
    """
    A fuel with name, price per tonne, energy coefficient and co_2 coefficient.

    :param name:
        The name
    :type name: str
    :param price: float
        Price in $ per tonne
    :param energy_coefficient:
    :param co2_coefficient: float
        Coefficient of produced CO_2 per amount of fuel
    """
    name: str
    price: float
    energy_coefficient: float
    co2_coefficient: float

    def to_json(self):
        # noinspection PyTypeChecker
        # Trade is an attrs instance.
        return attrs.asdict(self)

    def get_co2_emissions(self, amount):
        return amount * self.co2_coefficient

    def get_cost(self, amount):
        """
        :param amount: float
            Amount of fuel in tonnes
        :return: float
            The cost of the amount of fuel.
        """
        return amount * self.price


class VesselEngine:
    """
    An engine for a vessel that consumes fuel.
    """

    def __init__(self, fuel, idle_consumption, laden_consumption_rate, ballast_consumption_rate,
                 loading_consumption, unloading_consumption):
        """
        :param fuel: The fuel the engine uses.
        :type fuel: Fuel
        :param idle_consumption: The consumption of fuel while the vessel is idling.
            This should be a flat per time value.
        :type idle_consumption: float
        :param laden_consumption_rate: The consumption of fuel while the vessel is moving while laden.
            This is a speed dependent consumption curve.
        :type laden_consumption_rate: ConsumptionRate
        :param ballast_consumption_rate:
            The consumption of fuel while the vessel is moving while under ballast (unladen).
            This is a speed dependent consumption curve.
        :type ballast_consumption_rate: ConsumptionRate
        :param loading_consumption:
            The consumption of fuel while the vessel is loading.
            This should be a flat per time value.
        :type loading_consumption: float
        :param unloading_consumption:
            The consumption of fuel while the vessel is unloading.
            This should be a flat per time value.
        :type unloading_consumption: float
        """
        super().__init__()
        self._fuel = fuel
        self._idle_consumption = idle_consumption
        self._laden_consumption_rate = laden_consumption_rate
        self._ballast_consumption_rate = ballast_consumption_rate
        self._loading_consumption = loading_consumption
        self._unloading_consumption = unloading_consumption

    @attrs.define
    class Data(DataClass):
        fuel: str
        idle_consumption: float
        laden_consumption_rate: ConsumptionRate.Data
        ballast_consumption_rate: ConsumptionRate.Data
        loading_consumption: float
        unloading_consumption: float

        class Schema(DataSchema):
            fuel = fields.Str()
            idle_consumption = fields.Float()
            laden_consumption_rate = DynamicNestedField()
            ballast_consumption_rate = DynamicNestedField()
            loading_consumption = fields.Float()
            unloading_consumption = fields.Float()

            @post_load
            def _post_load(self, data, **kwargs):
                found_fuels = [f for f in global_setup.abc[FUEL_KEY] if f.name == data["fuel"]]
                first_fuel = None
                if len(found_fuels) > 0:
                    first_fuel = found_fuels.pop()
                data["fuel"] = first_fuel
                obj = super()._post_load(data)
                return obj

    @property
    def fuel(self):
        return self._fuel

    def get_idle_consumption(self, time):
        return self._idle_consumption * time

    def get_laden_consumption(self, time, speed):
        return self._get_speed_dependent_fuel_consumption(speed, time, self._laden_consumption_rate)

    def get_ballast_consumption(self, time, speed):
        return self._get_speed_dependent_fuel_consumption(speed, time, self._ballast_consumption_rate)

    def get_loading_consumption(self, time):
        return self._loading_consumption * time

    def get_unloading_consumption(self, time):
        return self._unloading_consumption * time

    @staticmethod
    def _get_speed_dependent_fuel_consumption(speed, time, consumption_function: ConsumptionRate):
        consumption = (consumption_function.base
                       * pow(speed, consumption_function.speed_power)
                       * consumption_function.factor
                       * time)
        return consumption

    def to_json(self):
        if isinstance(self._fuel, str):
            fuel_name = self._fuel
        else:
            fuel_name = self._fuel.name
        dict_repr = {"fuel": fuel_name,
                     "idle_consumption": self._idle_consumption,
                     "laden_consumption_rate": self._laden_consumption_rate.to_json(),
                     "ballast_consumption_rate": self._ballast_consumption_rate.to_json(),
                     "loading_consumption": self._loading_consumption,
                     "unloading_consumption": self._unloading_consumption}
        return dict_repr


class VesselWithEngine(WorldVessel):
    """
    A vessel with a fuel consuming engine.
    """

    def __init__(self, capacities_and_loading_rates, location, speed, propelling_engine,
                 keep_journey_log=True, name=None, company=None):
        """
        :param capacities_and_loading_rates: A list of the types, capacities and loading rates of the cargo containers.
        :type capacities_and_loading_rates: List[CargoCapacity]
        :param location: The location of the vessel at creation.
        :param speed: The vessels speed in knots (kn), i.e. nautical miles per hour (nmi/h).
        :type speed: float
        :param propelling_engine: The propelling engine.
        :type propelling_engine: VesselEngine
        :param keep_journey_log: If true the vessel keeps a log of event occurrences that affected the vessel.
        :type keep_journey_log: bool
        :param name: The name of the vessel.
        :type name: str
        :param company: The company that owns the vessel.
        :type company: ShippingCompany[V]
        """
        super().__init__(capacities_and_loading_rates, location, speed, keep_journey_log, name, company=company)
        self._propelling_engine = propelling_engine

    @attrs.define
    class Data(WorldVessel.Data):
        propelling_engine: VesselEngine.Data

        class Schema(WorldVessel.Data.Schema):
            propelling_engine = DynamicNestedField()

    @property
    def propelling_engine(self):
        return self._propelling_engine

    def get_co2_emissions(self, amount):
        """
        The amount of emitted co_2 for an amount of consumed fuel.

        :param amount: The amount of consumed fuel.
        :type amount: float
        :return: The amount of co_2.
        :rtype: float
        """
        return self._propelling_engine.fuel.get_co2_emissions(amount)

    def get_cost(self, amount):
        """
        The cost of burning the specified amount of fuel.

        :param amount: The amount of consumed fuel.
        :type amount: float
        :return: The cost of the amount of fuel.
        :rtype: float
        """
        return self._propelling_engine.fuel.get_cost(amount)

    def get_idle_consumption(self, time):
        """
        The amount of consumed fuel over a specified time idling.

        :param time: The time.
        :type time: float
        :return: The amount of fuel consumed.
        :rtype: float
        """
        return self._propelling_engine.get_idle_consumption(time)

    def get_laden_consumption(self, time, speed):
        """
        The amount of consumed fuel over a specified time in which the vessel is moving at speed while laden.

        :param time: The time.
        :type time: float
        :param speed: The speed of the vessel.
        :type speed: float
        :return: The amount of fuel consumed.
        :rtype: float
        """
        return self._propelling_engine.get_laden_consumption(time, speed)

    def get_ballast_consumption(self, time, speed):
        """
        The amount of consumed fuel over a specified time in which the vessel is moving at speed
        while under ballast (unladen).

        :param time: The time.
        :type time: float
        :param speed: The speed of the vessel.
        :type speed: float
        :return: The amount of fuel consumed.
        :rtype: float
        """
        return self._propelling_engine.get_ballast_consumption(time, speed)

    def get_loading_consumption(self, time):
        """
        The amount of consumed fuel over a specified time loading.

        :param time: The time.
        :type time: float
        :return: The amount of fuel consumed.
        :rtype: float
        """
        return self._propelling_engine.get_loading_consumption(time)

    def get_unloading_consumption(self, time):
        """
        The amount of consumed fuel over a specified time unloading.

        :param time: The time.
        :type time: float
        :return: The amount of fuel consumed.
        :rtype: float
        """
        return self._propelling_engine.get_unloading_consumption(time)

    def to_json(self):
        dict_repr = super().to_json()
        dict_repr.update({"propelling_engine": self._propelling_engine.to_json()})
        return dict_repr
