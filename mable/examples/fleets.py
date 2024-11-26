from typing import Tuple, List, Sequence, Union

import numpy as np

from mable.extensions.fuel_emissions import Fuel, ConsumptionRate, VesselWithEngine, VesselEngine
from mable.transport_operation import CargoCapacity


def get_fuel_mfo():
    """
    Return an 'MFO' fuel instance.

    :return: The fuel instance.
    :rtype Fuel
    """
    fuel_mfo = Fuel(name="MFO", price=1, energy_coefficient=40, co2_coefficient=3.16)
    return fuel_mfo


def default_laden_balast_consumption():
    """
    Returns laden and balast consumption curve specifications.

    :return: Tuple of laden and balast consumption.
    :rtype: Tuple[ConsumptionRate.Data, ConsumptionRate.Data]
    """
    laden_consumption_rate = ConsumptionRate.Data(
        ConsumptionRate,
        base=0.5503,
        speed_power=2.19201,
        factor=1 / 24)
    ballast_consumption_rate = ConsumptionRate.Data(
        ConsumptionRate,
        base=0.1493,
        speed_power=2.3268,
        factor=1 / 24)
    return laden_consumption_rate, ballast_consumption_rate


def example_fleet_1():
    """
    A fleet with one vessel docked in Aberdeen.

    :return: The fleet.
    :rtype: List[VesselWithEngine.Data]
    """
    laden_consumption_rate, ballast_consumption_rate = default_laden_balast_consumption()
    fleet = [VesselWithEngine.Data(
        VesselWithEngine,
        [CargoCapacity.Data(CargoCapacity, cargo_type="Oil", capacity=300000, loading_rate=5000)],
        "Aberdeen-f8ea5ddd09c3",
        speed=14,
        propelling_engine=VesselEngine.Data(
            VesselEngine,
            fuel=f"{get_fuel_mfo().name}",
            idle_consumption=7.13 / 24,
            laden_consumption_rate=laden_consumption_rate,
            ballast_consumption_rate=ballast_consumption_rate,
            loading_consumption=15.53 / 24,
            unloading_consumption=134.37 / 24),
        name="HMS Terror",
        keep_journey_log=True)]
    return fleet


def example_fleet_2():
    """
    A fleet with one vessel docked in Aberdeen.

    :return: The fleet.
    :rtype: List[VesselWithEngine.Data]
    """
    laden_consumption_rate, ballast_consumption_rate = default_laden_balast_consumption()
    fleet = [VesselWithEngine.Data(
        VesselWithEngine,
        [CargoCapacity.Data(CargoCapacity, cargo_type="Oil", capacity=300000, loading_rate=5000)],
        "Aberdeen-f8ea5ddd09c3",
        speed=14,
        propelling_engine=VesselEngine.Data(
            VesselEngine,
            f"{get_fuel_mfo().name}",
            idle_consumption=7.13 / 24,
            laden_consumption_rate=laden_consumption_rate,
            ballast_consumption_rate=ballast_consumption_rate,
            loading_consumption=15.53 / 24,
            unloading_consumption=134.37 / 24),
        name="HMS Erebus",
        keep_journey_log=True)]
    return fleet


def example_fleet_3():
    """
    A fleet with two vessel.

    :return: The fleet.
    :rtype: List[VesselWithEngine.Data]
    """
    fleet = example_fleet_2()
    laden_consumption_rate, ballast_consumption_rate = default_laden_balast_consumption()
    fleet.extend(
        [
            VesselWithEngine.Data(
                VesselWithEngine,
                [CargoCapacity.Data(CargoCapacity, cargo_type="Oil", capacity=300000, loading_rate=5000)],
                "Suez-4ad378ddd198",
                speed=14,
                propelling_engine=VesselEngine.Data(
                    VesselEngine,
                    f"{get_fuel_mfo().name}",
                    idle_consumption=7.13 / 24,
                    laden_consumption_rate=laden_consumption_rate,
                    ballast_consumption_rate=ballast_consumption_rate,
                    loading_consumption=15.53 / 24,
                    unloading_consumption=134.37 / 24),
                name="HMS Resolute",
                keep_journey_log=True)])
    return fleet


def mixed_fleet(num_suezmax=0, num_aframax=0, num_vlcc=0):
    """
    Returns a fleet with the specified number of
    Suezmax (capacity 145000), Aframax (capacity 100000), VLCC (capacity 285000) vessels.

    All vessels start in random locations and have random names.

    :param num_suezmax: The number of Suezmax vessels.
    :type num_suezmax: int
    :param num_aframax: The number of Aframax vessels.
    :type num_aframax: int
    :param num_vlcc: The number of VLCC vessels.
    :type num_vlcc: int
    :return: The fleet.
    :rtype: List[VesselWithEngine.Data]
    """
    fleet = []
    for i in range(num_suezmax):
        fleet.append(get_vessel_suezmax(f"HMS-S-{i}"))
    for i in range(num_aframax):
        fleet.append(get_vessel_aframax(f"HMS-A-{i}"))
    for i in range(num_vlcc):
        fleet.append(get_vessel_vlcc(f"HMS-V-{i}"))
    return fleet

def default_suezmax_aframax_laden_balast_consumption():
    """
    Returns laden and balast consumption curve specifications.

    :return: Tuple of laden and balast consumption.
    :rtype: Tuple[ConsumptionRate.Data, ConsumptionRate.Data]
    """
    laden_consumption_rate, ballast_consumption_rate = specified_laden_balast_consumption(
        laden_base=0.0473,
        laden_speed_power=2.6356,
        ballast_base=0.0195,
        ballast_speed_power=2.9185
    )
    return laden_consumption_rate, ballast_consumption_rate

def default_vlcc_laden_balast_consumption():
    """
    Returns laden and balast consumption curve specifications.

    :return: Tuple of laden and balast consumption.
    :rtype: Tuple[ConsumptionRate.Data, ConsumptionRate.Data]
    """
    laden_consumption_rate, ballast_consumption_rate = specified_laden_balast_consumption(
        laden_base=0.5503,
        laden_speed_power=2.19201,
        ballast_base=0.1493,
        ballast_speed_power=2.3268
    )
    return laden_consumption_rate, ballast_consumption_rate


def get_vessel(
        laden_consumption_rate, ballast_consumption_rate,
        idle_consumption, loading_consumption, unloading_consumption,
        capacity,
        name, port=None):
    """
    Generate a vessel based on the specifications.

    :param laden_consumption_rate: The laden consumption curve.
    :type laden_consumption_rate: ConsumptionRate.Data
    :param ballast_consumption_rate: The ballast consumption curve.
    :type ballast_consumption_rate: ConsumptionRate.Data
    :param idle_consumption: Fixed idle consumption per day.
    :type idle_consumption: float
    :param loading_consumption: Fixed loading consumption per day.
    :type loading_consumption: float
    :param unloading_consumption: Fixed unloading consumption per day.
    :type unloading_consumption: float
    :param capacity:
    :type capacity: float
    :param name: The name of the vessel.
    :param port: The starting port of the vessel. If None will be allocated at random.
    :type port: str | None
    :return: The vessel.
    :rtype: VesselWithEngine.Data
    """
    loading_rate = int(capacity/3.5)
    vessel = VesselWithEngine.Data(
        VesselWithEngine,
        [CargoCapacity.Data(CargoCapacity, cargo_type="Oil", capacity=capacity, loading_rate=loading_rate)],
        location=port,
        speed=14,
        propelling_engine=VesselEngine.Data(
            VesselEngine,
            f"{get_fuel_mfo().name}",
            idle_consumption=idle_consumption / 24,
            laden_consumption_rate=laden_consumption_rate,
            ballast_consumption_rate=ballast_consumption_rate,
            loading_consumption=loading_consumption / 24,
            unloading_consumption=unloading_consumption / 24),
        name=name,
        keep_journey_log=True)
    return vessel


def get_vessel_suezmax(name, port=None):
    """
    Generate a Suezmax vessel.

    :param name: The name of the vessel.
    :type name: str | None
    :param port: The starting port of the vessel. If None will be allocated at random.
    :type port: str | None
    :return: The vessel.
    :rtype: VesselWithEngine.Data
    """
    laden_consumption_rate, ballast_consumption_rate = default_suezmax_aframax_laden_balast_consumption()
    idle_consumption = 7.733
    loading_consumption = 12.23
    unloading_consumption = 79.5
    capacity = 145000
    vessel = get_vessel(
        laden_consumption_rate, ballast_consumption_rate,
        idle_consumption, loading_consumption, unloading_consumption,
        capacity,
        name=name, port=port)
    return vessel


def get_vessel_aframax(name, port=None):
    """
    Generate an Aframax vessel.

    :param name: The name of the vessel.
    :type name: str | None
    :param port: The starting port of the vessel. If None will be allocated at random.
    :type port: str | None
    :return: The vessel.
    :rtype: VesselWithEngine.Data
    """
    laden_consumption_rate, ballast_consumption_rate = default_suezmax_aframax_laden_balast_consumption()
    idle_consumption = 7.733
    loading_consumption = 12.23
    unloading_consumption = 79.5
    capacity = 100000
    vessel = get_vessel(
        laden_consumption_rate, ballast_consumption_rate,
        idle_consumption, loading_consumption, unloading_consumption,
        capacity,
        name=name, port=port)
    return vessel


def get_vessel_vlcc(name, port=None):
    """
    Generate a VLCC vessel.

    :param name: The name of the vessel.
    :type name: str | None
    :param port: The starting port of the vessel. If None will be allocated at random.
    :type port: str | None
    :return: The vessel.
    :rtype: VesselWithEngine.Data
    """
    laden_consumption_rate, ballast_consumption_rate = default_vlcc_laden_balast_consumption()
    idle_consumption = 7.13
    loading_consumption = 15.53
    unloading_consumption = 134.37
    capacity = 285000
    vessel = get_vessel(
        laden_consumption_rate, ballast_consumption_rate,
        idle_consumption, loading_consumption, unloading_consumption,
        capacity,
        name=name, port=port)
    return vessel


def specified_laden_balast_consumption(laden_base, laden_speed_power, ballast_base, ballast_speed_power):
    """
    Returns laden and balast consumption curve specifications.

    :return: Tuple of laden and balast consumption.
    :rtype: Tuple[ConsumptionRate.Data, ConsumptionRate.Data]
    """
    laden_consumption_rate = ConsumptionRate.Data(
        ConsumptionRate,
        base=laden_base,
        speed_power=laden_speed_power,
        factor=1 / 24)
    ballast_consumption_rate = ConsumptionRate.Data(
        ConsumptionRate,
        base=ballast_base,
        speed_power=ballast_speed_power,
        factor=1 / 24)
    return laden_consumption_rate, ballast_consumption_rate


def _get_random_capacity(base_capacity, random_capacity_range=None):
    capacity_factor = 0
    if random_capacity_range is not None:
        low = 0
        if isinstance(random_capacity_range, Sequence):
            if len(random_capacity_range) > 1:
                low = random_capacity_range[0]
                high = random_capacity_range[1]
            else:
                high = random_capacity_range[0]
        elif isinstance(random_capacity_range, Union[float, int]):
            high = random_capacity_range
        else:
            raise ValueError(f"random_capacity_range should be one or two numbers. Is {type(random_capacity_range)}")
        capacity_factor = np.random.uniform(low, high)
    capacity = base_capacity + capacity_factor
    return capacity
