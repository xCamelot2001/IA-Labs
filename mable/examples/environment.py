import os.path
import json
import threading
from zipfile import ZipFile
import pathlib
from typing import List, TYPE_CHECKING, Dict
from datetime import datetime

from loguru import logger

import mable.extensions.world_ports as world_ports
from mable.competition.generation import CompetitionBuilder, AuctionClassFactory
from mable.engine import SimulationEngine
from mable.event_management import IdleEvent
from mable.examples import fleets
from mable.extensions.fuel_emissions import FuelSpecsBuilder, VesselWithEngine
from mable.observers import (
    LogRunner, AuctionMetricsObserver, EventFuelPrintObserver, MetricsObserver, AuctionOutcomePrintObserver,
    TradeDeliveryObserver, AuctionOutcomeObserver)
from mable.simulation_space.universe import Location
from mable.util import JsonAbleEncoder

if TYPE_CHECKING:
    from mable.shipping_market import Trade


def get_specification_builder(
        environment_files_path=".",
        trade_occurrence_frequency=30,
        trades_per_occurrence=1,
        num_auctions=2,
        fixed_trades=None,
        use_only_precomputed_routes=True
    ):
    """
    Generate a specifications builder to specify a simulation settings.

    :param environment_files_path: The location of the environment files, i.e. the resources archive.
    :type environment_files_path: str
    :param trade_occurrence_frequency: The number of days between each auction occurrence. Default is 30 days.
    :type trade_occurrence_frequency: int
    :param trades_per_occurrence: The number of trades per auction occurrence. Default is 1.
    :type trades_per_occurrence: int
    :param num_auctions: The number of auctions. Default is 2.
    :type num_auctions: int
    :param fixed_trades: A list of fixed trades. Default is None.
        If fixed trades are specified, :paramref:`get_specification_builder.trade_occurrence_frequency`,
        :paramref:`get_specification_builder.trades_per_occurrence`
        and :paramref:`get_specification_builder.num_auctions` will be ignored.
    :type fixed_trades: List[Trade]
    :param use_only_precomputed_routes: Only generate cargoes between ports that have a precomputed route.
        Default is True.
    :type use_only_precomputed_routes: bool
    :return: The specification builder.
    :rtype: FuelSpecsBuilder
    :raises FileNotFoundError: If the resource file does not exist.
    """
    simulation_length = num_auctions * trade_occurrence_frequency
    specifications_builder = _get_specification_builder()
    _generate_environment(
        specifications_builder,
        environment_files_path=environment_files_path,
        trade_occurrence_frequency=trade_occurrence_frequency,
        trades_per_occurrence=trades_per_occurrence,
        simulation_length=simulation_length,
        fixed_trades=fixed_trades,
        use_only_precomputed_routes=use_only_precomputed_routes)
    return specifications_builder


def _get_specification_builder():
    specifications_builder = FuelSpecsBuilder()
    specifications_builder.add_fuel(fleets.get_fuel_mfo())
    return specifications_builder


def _generate_environment(specifications_builder, trade_occurrence_frequency,
                          trades_per_occurrence, simulation_length, environment_files_path=".",
                          fixed_trades=None, use_only_precomputed_routes=False):
    """
    Initialises the environment of the simulation.

    :param specifications_builder: The specifications builder that will be been used to specify a simulation settings.
    :type specifications_builder: FuelSpecsBuilder
    :param environment_files_path: The location of the environment files, i.e. the resources archive.
    :type environment_files_path: str
    :param use_only_precomputed_routes: Only generate cargoes between ports that have a precomputed route.
    :type use_only_precomputed_routes: bool
    :raises FileNotFoundError: If the resource file does not exist.
    """
    try:
        resource_files = {
            "precomputed_routes": "precomputed_routes.pickle",
            "routing_graph_world_mask": "routing_graph_world_mask.pkl",
            "time_transition_distribution": "time_transition_distribution.csv",
            "port_cargo_weight_distribution": "port_cargo_weight_distribution.csv",
            "port_trade_frequency_distribution": "port_trade_frequency_distribution.csv",
            "ports": "ports.csv"
        }
        resources_archive_path = os.path.join(environment_files_path, "mable_resources.zip")
        resources_archive = ZipFile(resources_archive_path)
        for one_resource_file_key in resource_files:
            if not os.path.isfile(resource_files[one_resource_file_key]):
                resources_archive.extract(resource_files[one_resource_file_key])
        real_ports = world_ports.get_ports(resource_files["ports"])
        specifications_builder.add_shipping_network(
            ports=real_ports,
            precomputed_routes_file=resource_files["precomputed_routes"],
            graph_file=resource_files["routing_graph_world_mask"])
        transition_duration_path = resource_files["time_transition_distribution"]
        cargo_weight_path = resource_files["port_cargo_weight_distribution"]
        trade_frequency_path = resource_files["port_trade_frequency_distribution"]
        precomputed_routes_file = None
        if use_only_precomputed_routes:
            precomputed_routes_file = resource_files["precomputed_routes"]
        if fixed_trades is None:
            specifications_builder.add_cargo_generation(
                port_transition_duration_distributions_path=transition_duration_path,
                port_cargo_weight_distribution_path=cargo_weight_path,
                port_trade_frequency_distribution_path=trade_frequency_path,
                trade_occurrence_frequency=trade_occurrence_frequency,
                trades_per_occurrence=trades_per_occurrence,
                simulation_length=simulation_length,
                precomputed_routes_file=precomputed_routes_file)
        else:
            specifications_builder.add_cargo_generation(static=True, fixed_trades=fixed_trades)
    except FileNotFoundError as e:
        logger.exception({f"Environment file(s) not found: {e}"})
        raise e


def generate_simulation(specifications_builder, show_detailed_auction_outcome=False, output_directory=".",
                        global_agent_timeout=60, info=None):
    """
    Generate a simulation from a specifications.

    :param specifications_builder: The specifications builder that has been used to specify a simulation settings.
    :type specifications_builder: FuelSpecsBuilder
    :param show_detailed_auction_outcome: Log the outcomes of auctions in detail.
    :type show_detailed_auction_outcome: bool
    :param output_directory: A directory to save the simulation output files.
    :type output_directory: str
    :param global_agent_timeout: The timeout in seconds of every agent action, e.g. one call to 'inform' or 'receive'.
        Default is 60 seconds.
    :type global_agent_timeout: int.
    :return: The simulation instance.
    :param info: Any information on the simulation.
    :type info: str | dict
    :rtype: SimulationEngine
    :raises ValueError: If the output directory does not exist.
    """
    if not pathlib.Path(output_directory).is_dir():
        raise ValueError(f"Output directory '{output_directory}' not found.")
    specifications = specifications_builder.build()
    sim_factory = CompetitionBuilder(AuctionClassFactory(), specifications)
    pre_run = ([LogRunner(logger, "---Pre Run Start---")]
               + SimulationEngine.PRE_RUN_CMDS
               + [LogRunner(logger, "--Run Start (Pre Run Finished)---")])
    post_run = [LogRunner(logger, "--Run Finished---"), _export_stats]
    sim = sim_factory.generate_engine(pre_run_cmds=pre_run, post_run_cmds=post_run, output_directory=output_directory,
                                      global_agent_timeout=global_agent_timeout, info=info)
    _activate_stats_collection(sim, show_detailed_auction_outcome)
    _activate_contract_fulfillment_check(sim)
    return sim


def _activate_stats_collection(simulation, show_detailed_auction_outcome=False):
    """
    Add the observers for stats collection.

    :param simulation: The simulation to observe.
    :type simulation: SimulationEngine
    """
    metric_observer = AuctionMetricsObserver()
    metric_observer.metrics.set_engine(simulation)
    simulation.register_event_observer(metric_observer)
    simulation.register_event_observer(EventFuelPrintObserver(logger))
    if show_detailed_auction_outcome:
        simulation.register_event_observer(AuctionOutcomePrintObserver(logger))

def _activate_contract_fulfillment_check(simulation):
    """
    Add the observers for stats collection.

    :param simulation: The simulation to observe.
    :type simulation: SimulationEngine
    """
    auction_outcome_observer = AuctionOutcomeObserver()
    simulation.register_event_observer(auction_outcome_observer)
    trade_delivery_observer = TradeDeliveryObserver()
    simulation.register_event_observer(trade_delivery_observer)


def _export_stats(simulation):
    """
    Export metrics to json.

    :param simulation: The simulation of which the metrics will be exported.
    :type simulation: SimulationEngine
    """

    for one_event_observer in simulation.get_event_observers():
        timestamp = datetime.today().strftime("%Y-%m-%d-%H-%M-%S")
        if isinstance(one_event_observer, MetricsObserver):
            _calculate_idle_times(simulation, one_event_observer)
            metrics = one_event_observer.metrics.to_json()
            metrics["global_metrics"]["penalty"] = _calculate_penalty(simulation, one_event_observer)
            metrics["info"] = simulation.info
            file_name = f"metrics_competition_{id(one_event_observer)}_{timestamp}.json"
            file_path = pathlib.Path(simulation.output_directory) / file_name
            with open(file_path, "w") as metrics_file:
                json.dump(metrics, metrics_file, indent=4, cls=JsonAbleEncoder)
            logger.info(f"Metrics exported to {file_path}")


def _check_threads(_):
    info_block = "\n=== Checking Active Threads ==="
    active_threads = threading.enumerate()
    info_block += f"\nTotal active threads: {len(active_threads)}"
    for thread in active_threads:
        info_block += f"\nThread: {thread.name}, Daemon: {thread.daemon}, Alive: {thread.is_alive()}"
    info_block += f"\n=== Finished Checking Active Threads ==="
    logger.info(info_block)


class _DummyIdling(IdleEvent):
    """
    An artificial idling event.
    """

    def __init__(self, time, vessel, time_started):
        super().__init__(time, vessel, Location(0, 0))
        self._time_started = time_started


def _calculate_idle_times(simulation, metrics_observer):
    """
    Calculate the idle time of all vessels.

    :param simulation: The simulation.
    :type simulation: SimulationEngine
    :return:
    """
    for one_company in simulation.shipping_companies:
        for one_vessel in one_company.fleet:
            idle_time = 0
            vessels_journey_log = one_vessel.journey_log
            last_time = 0
            sorted_events = sorted(vessels_journey_log, key=lambda x: x.time)
            for one_event in sorted_events:
                this_event_start = one_event.time_started
                time_gap = this_event_start - last_time
                if time_gap > 0:
                    idle_event = _DummyIdling(this_event_start, one_vessel, last_time)
                    metrics_observer.notify(simulation, idle_event, None)
                last_time = one_event.time
            time_gap = simulation.world.current_time - last_time
            if time_gap > 0:
                idle_event = _DummyIdling(simulation.world.current_time, one_vessel, last_time)
                metrics_observer.notify(simulation, idle_event, None)


def _calculate_penalty(simulation, metrics_observer):
    """
    Calculate breach of contract penalties.

    :param simulation: The simulation to check for unfulfilled contracts.
    :type simulation: SimulationEngine
    :param metrics_observer:

    :return: The penalties.
    :rtype: Dict[int, float]
    """
    penalties = {}
    for one_company in simulation.shipping_companies:
        if one_company in simulation.market_authority.contracts_per_company:
            all_contracts_of_company = simulation.market_authority.contracts_per_company[one_company]
            unfulfilled_contracts = [c for c in all_contracts_of_company if not c.fulfilled]
            penalty = 0
            biggest_vessel: VesselWithEngine = sorted(
                one_company.fleet[:], key=lambda x: x.capacity("Oil"), reverse=True)[0]
            for one_unfulfilled_contract in unfulfilled_contracts:
                trade_for_contract = one_unfulfilled_contract.trade
                loading_time = biggest_vessel.get_loading_time(trade_for_contract.cargo_type, trade_for_contract.amount)
                loading_consumption = biggest_vessel.get_loading_consumption(loading_time)
                distance_location_to_origin = simulation.headquarters.get_network_distance(
                    biggest_vessel.location, trade_for_contract.origin_port)
                travel_origin_time = biggest_vessel.get_travel_time(distance_location_to_origin)
                travel_origin_consumption = biggest_vessel.get_ballast_consumption(
                    travel_origin_time, biggest_vessel.speed)
                distance_origin_to_destination = simulation.headquarters.get_network_distance(
                    trade_for_contract.origin_port, trade_for_contract.destination_port)
                travel_destination_time = biggest_vessel.get_travel_time(distance_origin_to_destination)
                travel_destination_consumption = biggest_vessel.get_laden_consumption(
                    travel_destination_time, biggest_vessel.speed)
                total_consumption = loading_consumption * 2 + travel_origin_consumption + travel_destination_consumption
                total_fuel_cost = biggest_vessel.propelling_engine.fuel.get_cost(total_consumption)
                penalty += total_fuel_cost
        else:
            penalty = 0
        penalties[metrics_observer.metrics.get_company_id(one_company, create_id_if_not_exists=False)] = penalty
    return penalties
