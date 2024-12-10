"""
Extension to generate and transport cargoes based on cargo frequency and amount distributions
and associated changes to shipping.
"""
import pickle
from typing import Tuple

import numpy as np
import pandas as pd
import loguru

from mable.shipping_market import TimeWindowTrade
from mable.extensions.world_ports import LatLongFactory
from mable.event_management import ArrivalEvent
from mable.simulation_generation import SimulationBuilder
from mable.shipping_market import Shipping
from mable import instructions
from mable.util import format_time


logger = loguru.logger


class DistributionSimulationBuilder(SimulationBuilder):
    """
    Adjustments to simulation generation.
    """

    def generate_shipping(self, *args, **kwargs):
        """
        Keyword based generation.
        Otherwise, see py:func:`maritime_simulator.instructions.SimulationBuilder.generate_shipping`.
        """
        _, kwargs = self._specifications.get(instructions.SHIPPER_KEY)
        self._shipping = self._class_factory.generate_shipping(**kwargs, class_factory=self._class_factory,
                                                               world=self._world)
        return self


class TimeWindowArrivalEvent(ArrivalEvent):
    """
    An event where a vessel arrives for loading or unloading.
    """

    def __eq__(self, other):
        return (
                super().__eq__(other)
                and isinstance(other, TimeWindowArrivalEvent)
                and self._trade.time_window == other.trade.time_window)


class DistributionClassFactory(LatLongFactory):
    """
    Class factory to change the generation of classes to use the cargo distribution classes.
    """

    @staticmethod
    def generate_shipping(*args, **kwargs):
        return DistributionShipping(*args, **kwargs)

    @staticmethod
    def generate_trade(*args, **kwargs):
        return TimeWindowTrade(*args, **kwargs)

    @staticmethod
    def generate_event_arrival(*args, **kwargs):
        return TimeWindowArrivalEvent(*args, **kwargs)


class DistributionShipping(Shipping):
    """
    Generate cargoes based on cargo distributions.
    """

    def __init__(self, *args, **kwargs):
        self._time_transition_dist = None
        self._cargo_weight_dist = None
        self._frequency_dist = None
        self._trade_occurrence_frequency = kwargs['trade_occurrence_frequency'] * 24
        self._trades_per_occurrence = kwargs['trades_per_occurrence']
        self._simulation_length = kwargs['simulation_length']
        super().__init__(*args, **kwargs)

    @property
    def trade_occurrence_frequency(self):
        return self._trade_occurrence_frequency

    def initialise_trades(self, *args, **kwargs):
        """
        Generate all trades that occur over the run of the simulation.
        :param args:
            Ignored.
        :param kwargs:
            The paths to the cargo generation distributions.

            The paths to the csv files for the cargo generation as specified in :py:func:`load_distributions`:
                * port_transition_duration_distributions_path
                * port_cargo_weight_distribution_path
                * port_trade_frequency_distribution_path
        """
        world = kwargs["world"]
        del kwargs["world"]
        class_factory = kwargs["class_factory"]
        del kwargs["class_factory"]
        trade_occurrence_frequency = kwargs["trade_occurrence_frequency"] * 24
        del kwargs["trade_occurrence_frequency"]
        trades_per_occurrence = kwargs["trades_per_occurrence"]
        del kwargs["trades_per_occurrence"]
        simulation_length = kwargs["simulation_length"] * 24
        del kwargs["simulation_length"]
        precomputed_routes_file = kwargs["precomputed_routes_file"]
        del kwargs["precomputed_routes_file"]
        self.load_distributions(**kwargs)
        logger.debug(f"Generating trades from 0"
                     f" to {simulation_length} [at {format_time(simulation_length)}]"
                     f" every {trade_occurrence_frequency} [at {format_time(trade_occurrence_frequency)}]."
                     f" Resulting in {len(range(0, simulation_length + 1, trade_occurrence_frequency))}"
                     f" cargo events.")
        precomputed_routes = None
        if not precomputed_routes_file is None:
            with open(precomputed_routes_file, "rb") as f:
                precomputed_routes = pickle.load(f)
        for i in range(0, simulation_length + 1, trade_occurrence_frequency):
            pickup_period_days = (i/24, (i + trade_occurrence_frequency - 1)/24)
            cargoes_generated = self.sample_cargoes_from_port_distributions(
                world,
                class_factory,
                trades_per_occurrence,
                self._cargo_weight_dist,
                self._frequency_dist,
                self._time_transition_dist,
                pickup_period_days,
                time=i,
                precomputed_routes=precomputed_routes)
            logger.debug(f"Generated {len(cargoes_generated)} cargoes for time {i} [At {format_time(i)}].")
            self.add_to_all_trades(cargoes_generated)

    def load_distributions(self, port_transition_duration_distributions_path, port_cargo_weight_distribution_path,
                           port_trade_frequency_distribution_path):
        """
        Load the distributions for the cargo generation.

        :param port_transition_duration_distributions_path:
            The path to the csv with information on the transit durations.
        :param port_cargo_weight_distribution_path:
            The path to the csv with information on the average weight of cargo at the ports.
        :param port_trade_frequency_distribution_path:
            The path to the csv with information on the average visit frequency at the ports.
        """

        self._time_transition_dist = pd.read_csv(port_transition_duration_distributions_path)
        self._cargo_weight_dist = pd.read_csv(port_cargo_weight_distribution_path)
        self._frequency_dist = pd.read_csv(port_trade_frequency_distribution_path)

    @staticmethod
    def sample_cargo_weight(world, cargo_weight_dict, cargo_weight_distribution,
                            mean_cargo_weight_std, port, supply_demand):
        """Samples a cargo weight based on normal port distributions

        Parameters
        ----------
        world:
            TODO
        cargo_weight_dict: dict
            Stores cargo weight distributions that have already been searched for
        cargo_weight_distribution : pandas.DataFrame
            Distributions of the cargo weight picked up/delivered at individual ports
            Columns:
                Port: str
                    The name of the port
                SupplyDemand: str ("Supply" or "Demand", TODO: can be converted to binary)
                    Specifies if each row represents a supply or demand distribution
                Mean: float
                    The mean of the cargo weight normal distribution at the given port (picked up or delivered)
                Std. Dev: float or "inf", TODO: currently when only one data point, "inf" is passed by Lewis,
                                          TODO may be more appropriate to be empty
                    The standard deviation of the cargo weight normal distribution at the given port
                    (picked up or delivered)
        mean_cargo_weight_std: float
            The average standard deviation across all records in the cargo_weight_distribution.
            Used when std is missing.
        port: str
            The name of the port to sample at
        supply_demand: str
            String indicating if we look for 'Supply' or 'Demand' distribution

        :return:
        quantity : float
            The cargo quantity sampled (in MT)
        """
        if supply_demand != 'Supply' and supply_demand != 'Demand':
            raise ValueError("Incorrect trade mode given!")

        cargo_weight_record = cargo_weight_dict.get((port, supply_demand))
        if cargo_weight_record is None:
            cargo_weight_record = cargo_weight_distribution[(cargo_weight_distribution.Port == port) &
                                                            (cargo_weight_distribution.SupplyDemand
                                                             == supply_demand)].iloc[0]

            cargo_weight_dict[(port, supply_demand)] = cargo_weight_record

        cargo_weight_mean = cargo_weight_record['Mean']
        cargo_weight_std = cargo_weight_record['Std. Dev']

        # if std is missing for this record, take the average std
        if cargo_weight_std == float('inf'):
            cargo_weight_std = mean_cargo_weight_std

        # Sample from Gamma distribution fitted to the data
        scale = cargo_weight_std ** 2 / cargo_weight_mean
        shape = cargo_weight_mean/scale

        quantity = world.random.gamma(shape, scale)

        return quantity

    @staticmethod
    def sample_time_windows(world, time_transition_dict, time_transit_distribution,
                            mean_transition_std, start_port, end_port, cargo_weight, pickup_period,
                            time_windows_allowance=5):
        """Sample time interval based on normal time transition distributions between start and end ports

        Parameters
        ----------
        :param world: TODO
        :param time_transition_dict:
            Dictionary which stores the time transition times between port pairs
        :type time_transition_dict: dict
        :param time_transit_distribution :
            Distributions of the sailing time between ports
            Columns:
                From: str
                    The name of start port
                To: str
                    The name of end port
                Mean: float
                    The mean of the normal distribution of the sailing time (in minutes) between the start and end port
                Std. Dev: float or "inf", TODO: currently when only one data point, "inf" is passed by Lewis,
                                          TODO may be more appropriate to be empty
                    The standard deviation of the normal distribution of the sailing time between the start and end port
        :type time_transit_distribution: pd.DataFrame
        :param mean_transition_std: float
            The average standard deviation across all records in the time_transit_distribution.
            Used when std is missing.
        :param start_port : str
            The name of the start port
        :param end_port : str
            The name of the end port
        :param cargo_weight : float
            The cargo weight to be transported. It is used to calculate loading and unloading times
        :param pickup_period :
            The timestep interval in which trades needs to be picked up in days.
        :type pickup_period: Tuple[float, float]
        :param time_windows_allowance :
            The number of days (per directions) to extend each time window (default is 5)
        :type time_windows_allowance: int

        :return:
        pickup_time_window : tuple
            Pickup time window consisting representing the time interval the pickup should be started and finished
        delivery_time_window : tuple
            Pickup time window consisting representing the time interval the delivery should be started and finished
        """
        pickup_period_start_t = pickup_period[0]
        pickup_period_end_t = pickup_period[1]

        transition_record = time_transition_dict.get((start_port, end_port))
        if transition_record is None:
            transition_record = time_transit_distribution[((time_transit_distribution.From == start_port) &
                                                          (time_transit_distribution.To == end_port)) |
                                                          ((time_transit_distribution.From == end_port) &
                                                          (time_transit_distribution.To == start_port))].iloc[0]

            time_transition_dict[(start_port, end_port)] = transition_record
            time_transition_dict[(end_port, start_port)] = transition_record

        transition_mean = transition_record['Mean']
        transition_std = transition_record['Std. Dev']

        # if std is missing for this record, take the average std
        if transition_std == float('inf'):
            transition_std = mean_transition_std

        time_window_in_hours = world.random.normal(transition_mean, transition_std)

        # Convert from minutes to days
        time_window =  time_window_in_hours/(24 * 60)

        # TODO: extract from loading/unloading rate distributions when they exist
        port_loading_rate = 50000
        port_unloading_rate = 70000

        loading_time = int(cargo_weight/port_loading_rate)

        # Create pickup and delivery time windows to execute the sampled trade within the pickup time interval specified
        pickup_period_absolute_end_t = pickup_period_end_t - time_windows_allowance - loading_time
        pickup_time = world.random.randint(pickup_period_start_t, pickup_period_absolute_end_t)

        window_origin_earliest = max(0, pickup_time - time_windows_allowance)
        window_origin_latest = min(window_origin_earliest + 2 * time_windows_allowance, pickup_period_end_t)

        pickup_time_window = tuple(d * 24 for d in (window_origin_earliest, window_origin_latest))

        unloading_time = int(cargo_weight / port_unloading_rate)

        window_destination_earliest = window_origin_earliest + int(time_window) + unloading_time
        window_destination_latest = window_destination_earliest + 2 * time_windows_allowance

        delivery_time_window = tuple(d * 24 for d in (window_destination_earliest, window_destination_latest))

        return pickup_time_window, delivery_time_window

    @staticmethod
    def filter_out_outliers(df, stds_around_mean=5):
        mean_of_mean_column = df[df['Mean'] != float('inf')]['Mean'].mean(axis=0)
        std_of_mean_column = df[df['Mean'] != float('inf')]['Mean'].std(axis=0)

        mean_of_std_column = df[df['Std. Dev'] != float('inf')]['Std. Dev'].mean(axis=0)
        std_of_std_column = df[df['Std. Dev'] != float('inf')]['Std. Dev'].std(axis=0)

        # only return data that is within +/- std from the mean
        return df[
            (
                (
                    (mean_of_mean_column - std_of_mean_column * stds_around_mean <= df['Mean']) &
                    (df['Mean'] <= mean_of_mean_column + std_of_mean_column * stds_around_mean)
                )
                &
                (
                    (df['Std. Dev'] == float('inf'))
                    |
                    (
                        (df['Std. Dev'] != float('inf')) &
                        (
                            (mean_of_std_column - std_of_std_column * stds_around_mean <= df['Std. Dev']) &
                            (df['Std. Dev'] <= mean_of_std_column + std_of_std_column * stds_around_mean)
                        )
                    )

                )
            )
        ]

    def sample_cargoes_from_port_distributions(
            self,
            world,
            class_factory,
            number_of_cargoes,
            cargo_weight_distribution,
            frequency_distribution,
            time_transit_distribution,
            pickup_period,
            time,
            regional_changes=None,
            precomputed_routes=None):
        """Samples a given number of trades based on distributions.

        Parameters
        ----------
        number_of_cargoes : int
            The number of trades to be sampled
        cargo_weight_distribution : pandas.DataFrame
            Distributions of the cargo weight picked up/delivered at individual ports
            Columns:
                Port: str
                    The name of the port
                SupplyDemand: str ("Supply" or "Demand", TODO: can be converted to binary)
                    Specifies if each row represents a supply or demand distribution
                Mean: float
                    The mean of the cargo weight normal distribution at the given port (picked up or delivered)
                Std. Dev: float or "inf", TODO: currently when only one data point, "inf" is passed by Lewis,
                                          TODO may be more appropriate to be empty
                    The standard deviation of the cargo weight normal distribution
                    at the given port (picked up or delivered)
        frequency_distribution : pandas.DataFrame
            Distributions of the number of trades with cargo picked up/delivered at individual ports
            Columns:
                Name: str
                    The name of the port
                SupplyDemand: str ("Supply" or "Demand", TODO: can be converted to binary)
                    Specifies if each row represents a supply or demand distribution
                Num Samples: int
                    The number of trades at the given port (picked up or delivered as specified
                    in the SupplyDemand column)
        time_transit_distribution : pandas.DataFrame
            Distributions of the sailing time between ports
            Columns:
                From: str
                    The name of start port
                To: str
                    The name of end port
                Mean: float
                    The mean of the normal distribution of the sailing time (in minutes) between the start and end port
                Std. Dev: float or "inf", TODO: currently when only one data point, "inf" is passed by Lewis,
                                          TODO may be more appropriate to be empty
                    The standard deviation of the normal distribution of the sailing time between the start and end port
        pickup_period : (start_T, end_T) tuple
            The timestep interval in which trades needs to be picked up
        regional_changes : dict, optional
            TODO: implement regional changes
            A dictionary encoding the regional changes as passed from the web app (default is None)

        :return: list
            List of Cargo objects of length specified
        """

        new_cargoes = []
        cargo_weight_threshold = 1

        # Filter out outliers
        time_transit_distribution = self.filter_out_outliers(time_transit_distribution)
        cargo_weight_distribution = self.filter_out_outliers(cargo_weight_distribution)

        # Get average standard deviations to use when missing
        mean_transition_std = time_transit_distribution[time_transit_distribution['Std. Dev'] != float('inf')][
            'Std. Dev'].mean(axis=0)
        mean_cargo_weight_std = cargo_weight_distribution[cargo_weight_distribution['Std. Dev'] != float('inf')][
            'Std. Dev'].mean(axis=0)

        # Dictionaries to improve speed
        all_transition_ports = set(list(time_transit_distribution.From.values)
                                   + list(time_transit_distribution.To.values))
        cargo_weight_dict = {}
        time_transition_dict = {}
        demand_transition_dict = {}
        port_objects_dict = {}

        # To sample start ports, we only consider ports previously supplying cargo
        supply_data = frequency_distribution[frequency_distribution['SupplyDemand'] == 'Supply']

        total_supply_trades = np.sum(supply_data['Num Samples'].values)
        supply_probs = (supply_data['Num Samples'] / total_supply_trades).values

        # TODO: May result in an infinite loop if bad data is given
        while len(new_cargoes) < number_of_cargoes:
            # Sample a starting port based on historical frequency of trades starting from ports
            sampled_start_port_name = world.random.choice(supply_data['Port'].values, 1, replace=True, p=supply_probs)[0]

            # skip if no transition links exist
            if sampled_start_port_name not in all_transition_ports:
                continue

            sampled_start_port = port_objects_dict.get(sampled_start_port_name)
            if sampled_start_port is None:
                # skip if no location exist
                try:
                    sampled_start_port = world.network.get_port(sampled_start_port_name)
                    # start_port_long = start_port.longitude
                    # start_port_lat = start_port.latitude
                    # sampled_start_port_object = class_factory.generate_port(sampled_start_port,
                    #                                                         start_port_long,
                    #                                                         start_port_lat)

                    port_objects_dict[sampled_start_port] = sampled_start_port
                except KeyError:
                    logger.warning(f"Sampled port {sampled_start_port_name} not in network.")
                    continue

            # Sample supply cargo quantity
            supply_quantity = self.sample_cargo_weight(world, cargo_weight_dict, cargo_weight_distribution,
                                                       mean_cargo_weight_std, sampled_start_port_name,
                                                       supply_demand='Supply')

            # Sample end port from historical trades including the sampled start port
            demand_data_from_port = demand_transition_dict.get(sampled_start_port_name)
            if demand_data_from_port is None:
                time_transit_distribution_from = time_transit_distribution[time_transit_distribution.From
                                                                           == sampled_start_port_name]['To'].unique()
                time_transit_distribution_to = time_transit_distribution[time_transit_distribution.To
                                                                         == sampled_start_port_name]['From'].unique()
                existent_to_transitions = list(time_transit_distribution_from) + list(time_transit_distribution_to)

                demand_data_from_port = frequency_distribution[(frequency_distribution['SupplyDemand'] == 'Demand') &
                                                               (frequency_distribution['Port']
                                                                .isin(existent_to_transitions))]

                demand_transition_dict[sampled_start_port_name] = demand_data_from_port

            if len(demand_data_from_port['Num Samples'].values) == 0:
                # skip if no historical links from start port
                continue
            else:
                total_demand_trades = np.sum(demand_data_from_port['Num Samples'].values)
                demand_probs_from_port = (demand_data_from_port['Num Samples'] / total_demand_trades).values

            sampled_end_port_name = world.random.choice(demand_data_from_port['Port'].values, 1,
                                                        replace=True, p=demand_probs_from_port)[0]

            # skip if the ports selected coincide
            if sampled_start_port_name == sampled_end_port_name:
                continue

            # Do not proceed if precomputed routes are provided and route is  not in precomputed
            if not precomputed_routes is None:
                key_forward = f"{sampled_start_port_name}{sampled_end_port_name}"
                key_backwards = f"{sampled_end_port_name}{sampled_start_port_name}"
                if not (key_forward in precomputed_routes or key_backwards in precomputed_routes):
                    logger.warning(f"No precomputed route between sampled ports "
                                   f"{sampled_start_port_name} and {sampled_end_port_name}.")
                    continue

            sampled_end_port = port_objects_dict.get(sampled_end_port_name)
            if sampled_end_port is None:
                # skip if no location exist
                try:
                    sampled_end_port = world.network.get_port(sampled_end_port_name)
                    # end_port_long, end_port_lat = world.network.get_port(sampled_end_port_name)
                    # sampled_end_port_object = class_factory.generate_port(sampled_end_port_name,
                    #                                                       end_port_long,
                    #                                                       end_port_lat)

                    port_objects_dict[sampled_end_port_name] = sampled_end_port
                except KeyError:
                    logger.warning(f"Sampled port {sampled_start_port_name} not in network.")
                    continue

            # Sample demand cargo quantity
            demand_quantity = self.sample_cargo_weight(world, cargo_weight_dict, cargo_weight_distribution,
                                                       mean_cargo_weight_std, sampled_end_port_name,
                                                       supply_demand='Demand')

            # Finally, we take the smaller number out of the sampled demand
            # and supply quantity as a final cargo weight for the trade
            quantity = min(supply_quantity, demand_quantity)

            if quantity <= cargo_weight_threshold:
                continue

            # Get time windows
            pickup_time_window, delivery_time_window = self.sample_time_windows(world, time_transition_dict,
                                                                                time_transit_distribution,
                                                                                mean_transition_std,
                                                                                sampled_start_port_name,
                                                                                sampled_end_port_name,
                                                                                quantity, pickup_period)

            # create the sampled trade
            # TODO set an appropriate time
            sampled_trade = class_factory.generate_trade(
                    origin_port=sampled_start_port,
                    destination_port=sampled_end_port,
                    amount=quantity,
                    cargo_type="Oil",
                    time=time,
                    time_window=[
                        pickup_time_window[0],
                        pickup_time_window[1],
                        delivery_time_window[0],
                        delivery_time_window[1]]
                )
            new_cargoes.append(sampled_trade)
        return new_cargoes
