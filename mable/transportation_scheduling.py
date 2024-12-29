"""
Shipping operation
"""

from __future__ import annotations

from enum import IntEnum
import math
from itertools import product
from typing import TYPE_CHECKING, List, Tuple

import attrs
import networkx as nx
import numpy as np

from mable.shipping_market import TimeWindowTrade
from mable.simulation_environment import SimulationEngineAware
from mable.event_management import IdleEvent, TravelEvent

if TYPE_CHECKING:
    from mable.transport_operation import Vessel
    from mable.simulation_space.universe import Location, Port
    from mable.engine import SimulationEngine
    from mable.shipping_market import Trade


class TransportationSourceDestinationIndicator(IntEnum):
    PICK_UP = 0
    DROP_OFF = 1


class TransportationStartFinishIndicator(IntEnum):
    START = 0
    FINISH = 1

    def __repr__(self):
        str_repr = f"<{self.name}>"
        return str_repr


@attrs.define(kw_only=True)
class CurrentState:
    """
    The current state of a vessel including location and cargo loading.
    """
    current_time: float
    current_location: Location
    current_cargo_hold: dict
    vessel: Vessel
    engine: SimulationEngine
    is_valid: bool = True


class Schedule(SimulationEngineAware):
    """
    The schedule of a vessel.
    """

    def __init__(self, vessel, current_time=0, creation_time=0, schedule=None):
        """
        **Note**: Requires the engine to be set to work.

        :param vessel: The vessel for which the schedule is.
        :type vessel: Vessel
        :param schedule: Used for creating schedule copies (see :py:func:`schedule_copy`).
        Should be None for all purposes.
        """
        super().__init__()
        if schedule is None:
            self._stn = nx.DiGraph()
            self._stn.add_node(0)
        else:
            self._stn = schedule
        self._vessel = vessel
        self._time_schedule_head = current_time
        self._creation_time = creation_time
        self._next_event = None
        self._last_event = None

    @classmethod
    def init_with_engine(cls, vessel, current_time, engine):
        schedule = cls(vessel, current_time)
        schedule.set_engine(engine)
        return schedule

    @property
    def _number_tasks(self):
        task_indices = [n[0] for n in self._stn.nodes if isinstance(n, tuple)]
        total_number_tasks = len(set(task_indices))
        return total_number_tasks

    def copy(self):
        """
        Create a copy that contains the reference to the vessel but creates a deep copy of the actual schedule.

        :return: The copy
        :rtype: Schedule
        """
        copy_with_copy_stn = Schedule(
            self._vessel, current_time=self._time_schedule_head, creation_time=self._creation_time,
            schedule=self._stn.copy())
        copy_with_copy_stn.set_engine(self._engine)
        return copy_with_copy_stn

    def _shift_task_push(self, location, is_right_direction=True):
        shift_amount = 1
        if not is_right_direction:
            shift_amount = - 1
        if ((location + shift_amount, TransportationStartFinishIndicator.START) in self._stn
                or (location + shift_amount, TransportationStartFinishIndicator.FINISH) in self._stn):
            self._shift_task_push(location + shift_amount, is_right_direction)
        node_label_mapping = {
            (location, TransportationStartFinishIndicator.START):
                (location + shift_amount, TransportationStartFinishIndicator.START),
            (location, TransportationStartFinishIndicator.FINISH):
                (location + shift_amount, TransportationStartFinishIndicator.FINISH)
        }
        nx.relabel_nodes(self._stn, node_label_mapping, copy=False)

    def _shift_task_pull(self, location, is_right_direction=True):
        shift_amount = 1
        if not is_right_direction:
            shift_amount = - 1
        node_label_mapping = {
            (location, TransportationStartFinishIndicator.START):
                (location + shift_amount, TransportationStartFinishIndicator.START),
            (location, TransportationStartFinishIndicator.FINISH):
                (location + shift_amount, TransportationStartFinishIndicator.FINISH)
        }
        try:
            nx.relabel_nodes(self._stn, node_label_mapping, copy=False)
        except KeyError:
            pass  # No task to begin with. So, nothing to do.
        if ((location - shift_amount, TransportationStartFinishIndicator.START) in self._stn
                or (location - shift_amount, TransportationStartFinishIndicator.FINISH) in self._stn):
            self._shift_task_pull(location - shift_amount, is_right_direction)

    def _add_task_notes(self, location, trade, location_type):
        """
        Add the start and finish node of a task.

        :param location:
            The location of the task in the order of all tasks.
        :param trade:
            The task's associated trade.
        :param location_type:
            Either pick-up (:py:const:`TransportationSourceDestinationIndicator.PICK_UP`)
            or drop-off (:py:const:`TransportationSourceDestinationIndicator.DROP_OFF`).
        """
        if (location, TransportationStartFinishIndicator.START) in self._stn:
            self._shift_task_push(location)
        self._stn.add_nodes_from([
            ((location, TransportationStartFinishIndicator.START), {"trade": trade, "location_type": location_type}),
            ((location, TransportationStartFinishIndicator.FINISH), {"trade": trade, "location_type": location_type})
        ])

    def _get_travel_time(self, location, start_or_finish):
        """
        Calculate the travel time to a task or from a task.

        If start_or_finish is :py:const:`TransportationStartFinishIndicator.START` the travel time
        from the previous task to the task in the location is determined and if start_or_finish is
        :py:const:`TransportationStartFinishIndicator.FINISH` the travel time from the task in the location
        to the next task is determined.

        :param location:
            The location of the task in the order of all tasks.
        :type location: int

        :param start_or_finish:
            Either :py:const:`TransportationStartFinishIndicator.START`
            or :py:const:`TransportationStartFinishIndicator.FINISH`.
        :type start_or_finish: TransportationStartFinishIndicator
        :return:
            The travel time.
        :rtype: float
        """
        if start_or_finish not in [TransportationStartFinishIndicator.START, TransportationStartFinishIndicator.FINISH]:
            raise ValueError(f"The distance can only be to the start or after finish,"
                             f"i.e. 'start_or_finish' in "
                             f"[{TransportationStartFinishIndicator.START}, "
                             f"{TransportationStartFinishIndicator.FINISH}]")
        if start_or_finish == TransportationStartFinishIndicator.START:
            node_other = self._stn.nodes[(location - 1, TransportationStartFinishIndicator.FINISH)]
        else:
            node_other = self._stn.nodes[(location + 1, TransportationStartFinishIndicator.START)]
        if node_other["location_type"] == TransportationSourceDestinationIndicator.PICK_UP:
            location_other = node_other["trade"].origin_port
        else:
            location_other = node_other["trade"].destination_port
        node_current = self._stn.nodes[(location, start_or_finish)]
        if node_current["location_type"] == TransportationSourceDestinationIndicator.PICK_UP:
            location_current = node_current["trade"].origin_port
        else:
            location_current = node_current["trade"].destination_port
        if start_or_finish == TransportationStartFinishIndicator.START:
            travel_distance = self._engine.world.network.get_distance(location_other, location_current)
        else:
            travel_distance = self._engine.world.network.get_distance(location_current, location_other)
        travel_time = self._vessel.get_travel_time(travel_distance)
        return travel_time

    def _add_task_edges(self, location, location_type, cargo_transfer_time, earliest_start=0, latest_finish=math.inf):
        """
        Add the edges to and from a task.

        :param location:
            The location of the task in the order of all tasks.
        :param location_type: Indicator is it is a pick-up or drop-off. Values can be
            either pick-up (:py:const:`TransportationSourceDestinationIndicator.PICK_UP`)
            or drop-off (:py:const:`TransportationSourceDestinationIndicator.DROP_OFF`).
        :type location_type: int
        :param cargo_transfer_time:
            The time for cargo transfer. If this is loading or unloading depends on the task in the specified
            location.
        :param earliest_start:
        :param latest_finish:
        :return:
        """
        if location == 1:
            if location_type == TransportationSourceDestinationIndicator.PICK_UP:
                destination = self._stn.nodes[(1, TransportationStartFinishIndicator.START)]["trade"].origin_port
            else:
                destination = self._stn.nodes[(1, TransportationStartFinishIndicator.START)]["trade"].destination_port
            vessel_location = self._engine.world.network.get_vessel_location(self._vessel, self._engine.world.current_time)
            travel_distance = self._engine.world.network.get_distance(vessel_location, destination)
            travel_time = self._vessel.get_travel_time(travel_distance)
            arrival_time = travel_time + self._time_schedule_head
            operation_start = max(arrival_time, earliest_start)
            self._stn.add_edge((location, TransportationStartFinishIndicator.START), 0, weight=-operation_start)
        else:
            travel_time = self._get_travel_time(location, TransportationStartFinishIndicator.START)
            self._stn.add_edge((location, TransportationStartFinishIndicator.START),
                               (location - 1, TransportationStartFinishIndicator.FINISH),
                               weight=-travel_time)
            self._stn.add_edge((location - 1, TransportationStartFinishIndicator.FINISH),
                               (location, TransportationStartFinishIndicator.START),
                               weight=math.inf)
            self._stn.add_edge((location, TransportationStartFinishIndicator.START), 0, weight=-earliest_start)
        if (location + 1, TransportationStartFinishIndicator.START) in self._stn.nodes:
            travel_time = self._get_travel_time(location, TransportationStartFinishIndicator.FINISH)
            self._stn.add_edge((location + 1, TransportationStartFinishIndicator.START),
                               (location, TransportationStartFinishIndicator.FINISH),
                               weight=-travel_time)
            self._stn.add_edge((location, TransportationStartFinishIndicator.FINISH),
                               (location + 1, TransportationStartFinishIndicator.START),
                               weight=math.inf)
        self._stn.add_edge((location, TransportationStartFinishIndicator.START),
                           (location, TransportationStartFinishIndicator.FINISH), weight=math.inf)
        self._stn.add_edge((location, TransportationStartFinishIndicator.FINISH),
                           (location, TransportationStartFinishIndicator.START), weight=-cargo_transfer_time)
        self._stn.add_edge(0, (location, TransportationStartFinishIndicator.START), weight=latest_finish)
        self._stn.add_edge(0, (location, TransportationStartFinishIndicator.FINISH),
                           weight=latest_finish + cargo_transfer_time)
        self._stn.add_edge((location, TransportationStartFinishIndicator.FINISH), 0,
                           weight=-(earliest_start + cargo_transfer_time))

    def _add_task(self, location, trade, location_type, cargo_transfer_time):
        """
        Add the nodes for a task.

        :param location:
            The location of the task in the order of all tasks.
        :type location: int
        :param trade:
            The task's associated trade.
        :param location_type: Indicator is it is a pick-up or drop-off. Values can be
            either pick-up (:py:const:`TransportationSourceDestinationIndicator.PICK_UP`)
            or drop-off (:py:const:`TransportationSourceDestinationIndicator.DROP_OFF`).
        :type location_type: int
        :param cargo_transfer_time:
            The time for cargo transfer. If this is loading or unloading depends on the task in the specified
            location.
        :return:
        """
        if not isinstance(trade, TimeWindowTrade):
            trade = TimeWindowTrade(origin_port=trade.origin_port,
                                    destination_port=trade.destination_port,
                                    amount=trade.amount,
                                    cargo_type=trade.cargo_type,
                                    time=trade.time)
        self._add_task_notes(location, trade, location_type)
        possible_edges = [((location - 1, TransportationStartFinishIndicator.FINISH),
                           (location + 1, TransportationStartFinishIndicator.START)),
                          ((location + 1, TransportationStartFinishIndicator.START),
                           (location - 1, TransportationStartFinishIndicator.FINISH))]
        self._stn.remove_edges_from(possible_edges)
        if location_type == TransportationSourceDestinationIndicator.PICK_UP:
            earliest_start = trade.earliest_pickup_clean
            latest_finish = trade.latest_pickup_clean
        else:
            earliest_start = trade.earliest_drop_off_clean
            latest_finish = trade.latest_drop_off_clean
        self._add_task_edges(location, location_type, cargo_transfer_time,
                             earliest_start=earliest_start, latest_finish=latest_finish)

    def _add_relocation_task(self, index):
        """
        :param index:
            The index of the task in the order of all tasks.
        :type index: int
        """
        # TODO relocation tasks in STN.
        raise NotImplemented("Relocations are not implemented yet.")

    def _ensure_location_validity(self, location_pick_up, location_drop_off):
        if location_pick_up > location_drop_off:
            raise ValueError("Schedule locations are not compatible with the current schedule:"
                             " Trying to drop of cargo before picking it up.")
        elif (
                location_pick_up == 1
                and len(self) > 0
                and (1, TransportationStartFinishIndicator.START) not in self._stn):
            # TODO Write better error!
            raise ValueError("One or both schedule locations are not compatible with the current schedule.")
        elif location_pick_up > self._number_tasks + 1:
            # TODO Write better error!
            raise ValueError("One or both schedule locations are not compatible with the current schedule.")
        elif (
                location_pick_up != self._number_tasks + 1
                and location_drop_off > self._number_tasks + 1):
            # TODO Write better error!
            raise ValueError("One or both schedule locations are not compatible with the current schedule.")
        elif (

                location_pick_up == self._number_tasks + 1
                and location_drop_off > self._number_tasks + 2):
            # TODO Write better error!
            raise ValueError("One or both schedule locations are not compatible with the current schedule.")

    def add_transportation(self, trade, location_pick_up=None, location_drop_off=None):
        """
        Add a transportation into the schedule.

        :param trade: The task's associated trade.
        :type trade: Trade
        :param location_pick_up: The location of the pick-up task in the order of all tasks.
        :type location_pick_up: int
        :param location_drop_off: The location of the drop-off task in the order of all tasks.
        :type location_drop_off: int
        :raises: ValueError if the pick-up and drop-off indices are wrong.
        """
        if len(self) == 0:
            self._time_schedule_head = self._engine.world.current_time
            self._creation_time = self._engine.world.current_time
        if location_pick_up is None:
            location_pick_up = self.get_insertion_points()[-1]
        if location_drop_off is None:
            location_drop_off = location_pick_up
        self._ensure_location_validity(location_pick_up, location_drop_off)
        location_drop_off += 1
        cargo_transfer_time = self._vessel.get_loading_time(trade.cargo_type, trade.amount)
        self._add_task(location_pick_up, trade, TransportationSourceDestinationIndicator.PICK_UP, cargo_transfer_time)
        self._add_task(location_drop_off, trade, TransportationSourceDestinationIndicator.DROP_OFF, cargo_transfer_time)

    def add_relocation(self, port, index_in_schedule=None):
        """
        Add a relocation into the schedule.

        :param port: The port to relocate to.
        :type port: Port
        :param index_in_schedule: The index of the relocation in the schedule.
        :type index_in_schedule: int
        :raises: ValueError if the index is wrong.
        """
        if index_in_schedule is None:
            index_in_schedule = self.get_insertion_points()[-1]
        # TODO self._ensure_location_validity(location_start, location_end)
        self._add_relocation_task(index_in_schedule)


    def completion_time(self):
        """
        Determine the time when the schedule completes.

        :return: The completion time.
        :rtype: float
        """
        completion_time = 0
        start_compensator = 0
        finish_compensator = 0
        if len(self) > 0:
            task_combinations = ([(idx, indicator)
                                  for idx, indicator
                                  in product(range(2, self._number_tasks + 1),
                                             [TransportationStartFinishIndicator.START,
                                              TransportationStartFinishIndicator.FINISH])])
            if (1, TransportationStartFinishIndicator.START) in self._stn:
                edge_data = self._stn.get_edge_data((1, TransportationStartFinishIndicator.START), 0)
                start_compensator = edge_data["weight"]
                previous_task = (1, TransportationStartFinishIndicator.START)
                task_combinations = [(1, TransportationStartFinishIndicator.FINISH)] + task_combinations
            else:
                edge_data = self._stn.get_edge_data((1, TransportationStartFinishIndicator.FINISH), 0)
                previous_task = (1, TransportationStartFinishIndicator.FINISH)
                finish_compensator = edge_data["weight"]
            for idx, indicator in task_combinations:
                current_task = (idx, indicator)
                edge_data = self._stn.get_edge_data(
                    current_task,
                    previous_task)
                completion_time += edge_data["weight"]
                previous_task = current_task
        head_adjusted_finish_compensator = finish_compensator + self._time_schedule_head
        head_adjusted_start_compensator = start_compensator + self._time_schedule_head
        adjusted_completion_time = completion_time
        if finish_compensator < 0:
            adjusted_completion_time += head_adjusted_finish_compensator
        if head_adjusted_start_compensator < 0:
            adjusted_completion_time += head_adjusted_start_compensator
        adjusted_completion_time = - adjusted_completion_time
        completion_time = - completion_time
        k = self._time_schedule_head - self._creation_time
        if completion_time > 0:
            completion_time += -k + self._time_schedule_head
            adjusted_completion_time += -k + self._time_schedule_head
        if len(self) == 1:
            adjusted_completion_time += self._creation_time
        return adjusted_completion_time

    def _get_task_nodes(self):
        task_nodes = sorted([n for n in self._stn.nodes() if not n == 0])
        return task_nodes

    def _get_distance_matrix(self):
        nodes_in_order = [0] + self._get_task_nodes()
        matrix = nx.to_numpy_array(self._stn, nodes_in_order, nonedge=np.nan)
        return matrix

    def _get_node_locations(self):
        nodes_world_locations = [self._stn.nodes[t]["trade"].origin_port
                                 if self._stn.nodes[t]["location_type"] == TransportationSourceDestinationIndicator.PICK_UP
                                 else self._stn.nodes[t]["trade"].destination_port
                                 for t in sorted([n for n in self._stn.nodes if isinstance(n, tuple)])]
        return nodes_world_locations

    def verify_schedule_time(self):
        """
        Verifies that the schedule's timing is possible. A schedule is valid is it has no negative cycles.

        :return: True is the schedule is valid, False otherwise.
        :rtype: bool
        """
        # TODO Going through all cycles seems like a bad idea but negative_edge_cycle seems to not work reliably.
        # At least sometimes it is False despite there being a negative cycle
        # has_negative_cycle = nx.negative_edge_cycle(self._stn)
        has_negative_cycle = False
        all_cycles = nx.simple_cycles(self._stn)
        try:
            while not has_negative_cycle:
                cycle = next(all_cycles)
                weight = sum(self._stn[u][v]['weight'] for u, v in zip(cycle, cycle[1:] + [cycle[0]]))
                if weight < 0:
                    has_negative_cycle = True
        except StopIteration:
            pass  # Nothing to do all cycles tested
        is_valid_schedule = not has_negative_cycle
        return is_valid_schedule

    def verify_schedule_cargo(self):
        """
        Verifies that the schedule's cargo loading and unloading is possible.
        The verification is done via simulating all loading and unloading events.

        :return: True is the schedule is valid, False otherwise.
        :rtype: bool
        """
        current_cargo_hold = self._vessel.copy_hold()
        i = 1
        valid_schedule = True
        while valid_schedule and i < self._number_tasks + 1:
            current_task_node = self._stn.nodes[(i, TransportationStartFinishIndicator.FINISH)]
            current_task_type = current_task_node["location_type"]
            current_task_trade = current_task_node["trade"]
            try:
                if current_task_type is TransportationSourceDestinationIndicator.PICK_UP:
                    current_cargo_hold.load_cargo(current_task_trade.cargo_type, current_task_trade.amount)
                else:
                    current_cargo_hold.unload_cargo(current_task_trade.cargo_type, current_task_trade.amount)
            except ValueError:
                valid_schedule = False
            i += 1
        is_valid_schedule = valid_schedule and current_cargo_hold.is_empty()
        return is_valid_schedule

    def verify_schedule(self):
        """
        Verify that a schedule can be completed in time and without over-/under-loading the cargo hold.
        This is convenience function that combines :func:`verify_schedule_time` and :func:`verify_schedule_cargo`.

        :return: True if the timing and the cargo load are valid over all tasks and associated trades. Otherwise, False.
        :rtype: bool
        """
        valid_schedule = self.verify_schedule_time() and self.verify_schedule_cargo()
        return valid_schedule

    def get_insertion_points(self):
        """
        Get the points where tasks can be inserted.

        :return: List of insertion points.
        :rtype: List[int]
        """
        if self._number_tasks == 0:
            insertion_points = [1]
        else:
            # +1 for starting at one (not zero indexed), +1 for finishing task after last task
            insertion_points_range_adjustment = 2
            if (1, TransportationStartFinishIndicator.START) in self._stn.nodes:
                insertion_points = range(1, self._number_tasks + insertion_points_range_adjustment)
            else:
                insertion_points = range(2, self._number_tasks + insertion_points_range_adjustment)
        return insertion_points

    def get_simple_schedule(self):
        """
        Produce a simple overview of the schedule in the form of a list with drop off/pick up indicator and
        associated cargo, e.g. [('PICK_UP', <trade>), ('DROP_OFF', <trade>)].

        :return: The simple overview.
        :rtype: List[Tuple[str, Trade]]
        """
        simple_schedule = [None] * self._number_tasks
        for one_task in iter(self._stn):
            task_idx = None
            if isinstance(one_task, tuple):
                task_idx = one_task[0]
            if task_idx is not None:
                if one_task[1] == TransportationStartFinishIndicator.FINISH:
                    node = self._stn.nodes[one_task]
                    location_type, current_trade = self._get_node_info(node)
                    simple_schedule[task_idx - 1] = (location_type.name , current_trade)
        return simple_schedule

    def get_scheduled_trades(self):
        """
        List of all trades that are scheduled to be transported.

        :return: The trades.
        :rtype: List[Trade]
        """
        trades = []
        for one_task in iter(self._stn):
            task_idx = None
            if isinstance(one_task, tuple):
                task_idx = one_task[0]
            if task_idx is not None:
                if one_task[1] == TransportationStartFinishIndicator.FINISH:
                    node = self._stn.nodes[one_task]
                    location_type, current_trade = self._get_node_info(node)
                    if location_type == TransportationSourceDestinationIndicator.DROP_OFF:
                        trades.append(current_trade)
        return trades

    def __len__(self):
        """
        The length in events. Which are usually (i.e. if not partially fulfilled) twice the number of tasks
        or four times the number of trades.

        :return: #Events
        :rtype: int
        """
        return len(self._stn.nodes) - 1

    def _get_node(self, idx):
        """
        Retrieve the node based on the indices of the tasks in the scheduled. The tasks are ordered by their order in
        the schedule.

        :param idx: The tasks index.
        :return: The node.
        :raises IndexError: If the index does not exist
        """
        task = (1, TransportationStartFinishIndicator.START)
        if task not in self._stn:
            task = (1, TransportationStartFinishIndicator.FINISH)
        if idx < 0:
            num_nodes = len(self._stn.nodes)
            i = num_nodes + idx - 1  # - 1 for 0 is not a valid node.
            if i < 0:
                raise IndexError(idx)
        else:
            i = idx
        while i > 0:
            if task[1] == TransportationStartFinishIndicator.START:
                task = (task[0], TransportationStartFinishIndicator.FINISH)
            else:
                task = (task[0] + 1, TransportationStartFinishIndicator.START)
            i -= 1
        try:
            node = self._stn.nodes[task]
        except KeyError:
            raise IndexError(idx)
        return task, node

    @staticmethod
    def _get_vessel_destination(node):
        location_type, current_trade = Schedule._get_node_info(node)
        if location_type == TransportationSourceDestinationIndicator.PICK_UP:
            vessel_destination = current_trade.origin_port
        else:
            vessel_destination = current_trade.destination_port
        return vessel_destination

    @staticmethod
    def _get_trade_location_and_time(node):
        location_type, current_trade = Schedule._get_node_info(node)
        is_pickup = not location_type
        if is_pickup:
            location = current_trade.origin_port
            earliest_event_time = current_trade.earliest_pickup
        else:
            location = current_trade.destination_port
            earliest_event_time = current_trade.earliest_drop_off
        return location, earliest_event_time

    @staticmethod
    def _get_node_info(node):
        """
        :param node:
        :return The type of location and the trade.
        :rtype: Tuple[
        """
        location_type = None
        current_trade = None
        try:
            location_type = node["location_type"]
            current_trade = node["trade"]
        except KeyError:
            pass  # Nothing to do
        return location_type, current_trade

    def _generate_arrival_or_travel_or_idle_event(self, node):
        location_type, current_trade = Schedule._get_node_info(node)
        is_pickup = not location_type
        vessel_location = self._vessel.location
        vessel_destination = self._get_vessel_destination(node)
        trade_location, earliest_event_time = Schedule._get_trade_location_and_time(node)
        idle_time = 0
        if earliest_event_time is not None:
            idle_time = max(earliest_event_time - self._time_schedule_head, 0)
        is_or_will_be_in_location = (vessel_location == vessel_destination
                                     or (isinstance(self._last_event, TravelEvent)
                                         and self._last_event.location.destination == vessel_destination))
        is_ready_for_loading = is_or_will_be_in_location and idle_time == 0
        if is_ready_for_loading:
            event_time = self._time_schedule_head
            event = self._engine.class_factory.generate_event_arrival(event_time, self._vessel,
                                                                      current_trade, is_pickup=is_pickup)
        elif not is_or_will_be_in_location:
            event = self._generate_travel_event(node)
        else:
            event = self._engine.class_factory.generate_event_idling(earliest_event_time, self._vessel, trade_location)
        return event

    def _generate_travel_event(self, node):
        """
        Generate a travel event for a node.

        **Warning** The time of the event is only reliable if the node is the first task in the schedule.

        :param node: The node.
        :return: The event.
        """
        vessel_location = self._engine.world.network.get_vessel_location(self._vessel, self._engine.world.current_time)
        vessel_destination = self._get_vessel_destination(node)
        travel_distance = self._engine.world.network.get_distance(vessel_location, vessel_destination)
        event_time = self._vessel.get_travel_time(travel_distance)
        event_time += self._time_schedule_head
        event = self._engine.class_factory.generate_event_travel(event_time, self._vessel,
                                                                 vessel_location, vessel_destination)
        return event

    def _generate_cargo_transfer_event(self, node):
        """
        Generate a cargo transfer event for a node.

        **Warning** The time of the event is only reliable if the node is the first task in the schedule.

        :param node: The node.
        :return: The event.
        """
        location_type, current_trade = Schedule._get_node_info(node)
        is_pickup = not location_type
        event_time = self._vessel.get_loading_time(current_trade.cargo_type, current_trade.amount)
        event_time += self._time_schedule_head
        event = self._engine.class_factory.generate_event_cargo_transfer(event_time, self._vessel,
                                                                         current_trade, is_pickup=is_pickup)
        return event

    def __getitem__(self, idx):
        task, node = self._get_node(idx)
        if task[1] == TransportationStartFinishIndicator.START:
            event = self._generate_arrival_or_travel_or_idle_event(node)
        else:
            event = self._generate_cargo_transfer_event(node)
        return event

    def get(self, idx, default=None):
        try:
            event = self[idx]
        except IndexError:
            event = default
        return event

    def _get_first_node(self):
        first_node = None
        if self._number_tasks > 0:
            first_node = (1, TransportationStartFinishIndicator.START)
            if first_node not in self._stn.nodes:
                first_node = (1, TransportationStartFinishIndicator.FINISH)
        return first_node

    def pop(self):
        """
        Pop the next scheduled location.

        :return: The next stop.
        """
        event = self.next()
        self._last_event = event
        self._next_event = None
        no_node_shift_events = [IdleEvent, TravelEvent]
        next_event_is_no_shift_event = any(isinstance(event, one_no_shift_event_type)
                                           for one_no_shift_event_type in no_node_shift_events)
        if not next_event_is_no_shift_event:
            first_node = self._get_first_node()
            self._stn.remove_node(first_node)
            if first_node == (1, TransportationStartFinishIndicator.FINISH):
                self._shift_task_pull(2, False)
        self._time_schedule_head = event.time
        first_node = self._get_first_node()
        if first_node is not None:
            next_event = self.next()
            self._stn[first_node][0]["weight"] = min(self._stn[first_node][0]["weight"], -next_event.time)
        return event

    def next(self):
        """
        Get the next scheduled location or None if the schedule is empty.

        :return: The next stop.
        """
        if self._next_event is None:
            self._next_event = self.get(0)
        return self._next_event
