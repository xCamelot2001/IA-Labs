"""
Ports and routing based on a world graph and real world port location.
"""

import csv
import itertools
import math
import os
import pickle
from typing import List, TYPE_CHECKING

import numpy as np
import loguru
import networkx
from simplification.cutil import simplify_coords

from mable.simulation_space.universe import Port, Location, OnJourney
from mable.simulation_space.structure import NetworkWithPortDict
from mable import simulation_generation
from mable.transport_operation import SimpleVessel
from mable.util import JsonAble

if TYPE_CHECKING:
    from mable.transport_operation import CargoCapacity, Vessel


logger = loguru.logger


class LatLongFactory(simulation_generation.ClassFactory):
    """
    Factory to generate the network, ports and vessels in a real-world graph.
    """

    @staticmethod
    def generate_network(*args, **kwargs):
        return LatLongShippingNetwork(*args, **kwargs)

    @staticmethod
    def generate_port(*args, **kwargs):
        return LatLongPort(*args, **kwargs)

    @staticmethod
    def generate_location(*args, **kwargs):
        return LatLongLocation(*args, **kwargs)

    @staticmethod
    def generate_vessel(*args, **kwargs):
        return WorldVessel(*args, **kwargs)


class LatLongLocation(Location):
    """
    A location with latitude and longitude.
    """

    def __init__(self, latitude, longitude, name):
        super().__init__(latitude, longitude, name)

    @property
    def latitude(self):
        return self.x

    @property
    def longitude(self):
        return self.y


class LatLongPort(Port, JsonAble):
    """
    A port with latitude and longitude.
    """

    def __init__(self, name, latitude, longitude):
        """
        :param name: The name of the port.
        :type name: str
        :param latitude: The latitude of the port in decimal degrees.
        :type latitude: float
        :param longitude: The longitude of the port in decimal degrees.
        :type longitude: float
        """
        super().__init__(name, latitude, longitude)

    @property
    def latitude(self):
        """
        :return: The latitude of the port in decimal degrees.
        :rtype: float
        """
        return self.x

    @property
    def longitude(self):
        """
        :return: The longitude of the port in decimal degrees.
        :rtype: float
        """
        return self.y

    def to_json(self):
        """
        :return: The port information as dictionary with keys 'name', 'latitude' and 'longitude'.
        :rtype: dict
        """
        dict_for_json = {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude
        }
        return dict_for_json


class WorldVessel(SimpleVessel):

    def __init__(self, capacities_and_loading_rates, location, speed, keep_journey_log=True, name=None, company=None):
        """
        :param capacities_and_loading_rates: A list of the types, capacities and loading rates of the cargo containers.
        :type capacities_and_loading_rates: List[CargoCapacity]
        :param location: The location of the vessel at creation.
        :param speed: The vessels speed in knots (kn), i.e. nautical miles per hour (nmi/h).
        :type speed: float
        :param keep_journey_log: If true the vessel keeps a log of event occurrences that affected the vessel.
        :type keep_journey_log: bool
        :param name: The name of the vessel.
        :type name: str
        :param company: The company that owns the vessel.
        :type company: ShippingCompany[V]
        """
        super().__init__(
            capacities_and_loading_rates, location, speed, keep_journey_log=keep_journey_log, name=name, company=company)

    def get_travel_time(self, distance, *args, **kwargs):
        """
        The time it takes to travel the specified distance.

        :param distance: Distance in nautical miles (nmi).
        :type distance: float
        :return: The travel time in hours (h).
        :rtype: float
        """
        return super().get_travel_time(distance, *args, **kwargs)


def get_index_or_default(search_list, search_term, default=0):
    """
    Returns the first index of the elements who contain the search term or the default if no element matches.
    :param search_list:
        The list to search in.
    :param search_term:
        The search term.
    :param default:
        The default to return if no element matches. Default value is 0.
    :return:
        The index of the first match or the default.
    """
    indices_with_term = [idx for idx in range(len(search_list)) if search_term in search_list[idx].lower()]
    if len(indices_with_term) > 0:
        idx = indices_with_term[0]
    else:
        idx = default
    return idx


def get_ports(path):
    """
    Retrieve the ports from a csv file.
    :param path:
        The path of the port file.
    :return: list
        A list of the ports
    """
    with open(path, mode='r') as ports_file:
        has_header = csv.Sniffer().has_header(ports_file.read(1024))
        ports_file.seek(0)
        ports_csv_file = csv.reader(ports_file)
        idx_name = 0
        idx_lat = 1
        idx_long = 2
        if has_header:
            header = next(ports_csv_file)
            idx_name = get_index_or_default(header, "name", idx_name)
            idx_lat = get_index_or_default(header, "latitude", idx_lat)
            idx_long = get_index_or_default(header, "longitude", idx_long)
        ports = []
        for line in ports_csv_file:
            name = line[idx_name].strip()
            lat = float(line[idx_lat].strip())
            long = float(line[idx_long].strip())
            port_in_line = LatLongPort(name, lat, long)
            ports.append(port_in_line)
        return ports


class LatLongShippingNetwork(NetworkWithPortDict):
    """
    A shipping network with latitude on longitude locations.
    """

    def __init__(self, ports=None, precomputed_routes_file=None, graph_file=None):
        super().__init__(ports)
        self._precomputed_routes_file = precomputed_routes_file
        self._precomputed_routes = None
        if self._precomputed_routes_file is not None:
            with open(self._precomputed_routes_file, 'rb') as file:
                self._precomputed_routes = pickle.load(file)
        self._graph_file = graph_file
        # canals
        self.canals = {
            "Suez": (LatLongLocation(32.5, 31.245, 'Suez canal start'),
                     LatLongLocation(32.9, 29.15, 'Suez canal end')),
            "Panama": (LatLongLocation(-79.5832, 8.7498, 'Panama canal start'),
                       LatLongLocation(-80, 9.5833, 'Panama canal end')),
        }
        # lazy load the world graph, no need to do this unless a route is not in the DB (which shouldn't happen)
        self._world_graph = None
        self._canals_nodes = None
        self._scenarios = None

    @property
    def world_graph(self):
        if self._world_graph is None and self._graph_file is not None:
            self._world_graph = self.generate_route_graph_from_file()
        return self._world_graph

    @property
    def canals_nodes(self):
        """
        Return locations which are canals
        :return:
            The canals.
        """
        if self._canals_nodes is None:
            self._canals_nodes = self.create_canal_nodes()
        return self._canals_nodes

    @property
    def scenarios(self):
        """
        Return canal scenarios. See :py:func:`LatLongShippingNetwork.create_world_canal_scenarios`

        :return: The scenarios.
        """
        if self._scenarios is None:
            self._scenarios = self.create_world_canal_scenarios()
        return self._scenarios

    def get_distance(self, location_one, location_two):
        """
        Get the distance between two locations.

        If there is no route between the two locations infinity (math.inf) if returned.

        :param location_one: The first location.
        :type location_one: Port | str
        :param location_two: The second location.
        :type location_one: Port | str
        :return: The distance or math.inf if no route between the two locations exists.
        :rtype: float
        """
        if isinstance(location_one, OnJourney) or isinstance(location_two, OnJourney):
            raise TypeError("OnJourney is not a valid fixed location. Two fixed locations required.")
        if not isinstance(location_one, Location):
            location_one = self.get_port(location_one)
        if not isinstance(location_two, Location):
            location_two = self.get_port(location_two)
        if location_one == location_two:
            distance = 0
        else:
            route = self.get_shortest_path_between_points(location_one, location_two)
            distance = math.inf
            if route is not None:
                distance = route.length
        return distance

    def _get_precomputed_routes(self, location_one, location_two):
        routes = None
        index_one = f"{location_one.name}{location_two.name}"
        index_two = f"{location_two.name}{location_one.name}"
        if self._precomputed_routes is not None:
            if index_one in self._precomputed_routes or index_two in self._precomputed_routes:
                if index_one in self._precomputed_routes:
                    routes = self._precomputed_routes[index_one]
                else:
                    routes = self._precomputed_routes[index_two]
                    for route in routes:
                        route.route = list(reversed(route.route))
                        route.canals = list(reversed(route.canals))
            else:
                logger.warning(f"Routes entry for routes between '{location_one.name}'"
                               f" and '{location_two.name}' not found.")
        return routes

    @staticmethod
    def get_long_lat_dist(lat_a, lng_a, lat_b, lng_b):
        """
        Calculate the distance between points on earth using the haversine distance,
        assuming the earth is a perfect sphere.
        """
        d_lon = math.radians(lng_b - lng_a)
        d_lat = math.radians(lat_b - lat_a)

        a = (math.sin(d_lat / 2) ** 2
             + math.cos(math.radians(lat_a)) * math.cos(math.radians(lat_b)) * math.sin(d_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        earth_radius = 6371000  # earth radius in m
        distance = earth_radius * c

        return distance

    def get_journey_location(self, journey, vessel, current_time):
        """
        Returns the current position of the vessel based on the journey information and the current time.

        :param journey: The journey object.
        :type journey: OnJourney
        :param vessel: The vessel that is performing the journey.
        :type vessel: Vessel
        :param current_time: The current time.
        :type current_time: float
        :return: The current location the vessel is in.
        :rtype: Location
        """
        origin = journey.origin
        destination = journey.destination
        route = self.get_shortest_path_between_points(origin, destination)
        travel_time = vessel.get_travel_time(route.length)
        time_travelled = current_time - journey.start_time
        if time_travelled == 0:
            location = journey.origin
        elif time_travelled >= travel_time:
            location = journey.destination
        else:
            route_origin_to_destination = list(reversed(route.route))
            percentage_travel = time_travelled/travel_time
            distance_travelled = percentage_travel * route.length
            segment_distances_dist = [
                self.compute_route_length([route_origin_to_destination[i], route_origin_to_destination[i + 1]])
                for i in range(len(route_origin_to_destination) - 1)]
            route_distance: list[float] = [sum(segment_distances_dist[:i]) for i in range(len(segment_distances_dist))]
            route_distance.append(route.length)
            idx_in_route = next(i for i in range(len(route_distance)) if route_distance[i] > distance_travelled) - 1
            # TODO the calculation of an intermediate point on a segment does not seem to work
            # distance_on_segment = distance_travelled - route_distance[idx_in_route]
            # percentage_on_segment = distance_on_segment/segment_distances_dist[idx_in_route]
            # route_segment = route.route[idx_in_route:idx_in_route + 2]
            # location = LatLongLocation(
            #     route_segment[0][1] + percentage_on_segment * (route_segment[1][1] - route_segment[0][1]),
            #     route_segment[0][0] + percentage_on_segment * (route_segment[1][0] - route_segment[0][0]),
            #     ""
            # )
            last_segment_start = route_origin_to_destination[idx_in_route]
            location = LatLongLocation(
                last_segment_start[1],
                last_segment_start[0],
                f"<{last_segment_start[1]}, {last_segment_start[0]}>"
            )
        return location

    def generate_route_graph_from_file(self):
        """
        Generates the router graph file depending on the type of file the router has been initialised with
        Returns
        -------

        graph: networkx graph
            the graph generated from the file
        """
        name, file_extension = os.path.splitext(self._graph_file)
        graph = None
        if file_extension == ".txt":
            # create world routing graph from a precomputed file
            matrix = np.loadtxt(self._graph_file)
            graph = networkx.Graph()
            for n1_long, n1_lat, n2_long, n2_lat, w in matrix:
                graph.add_edge((n1_long, n1_lat), (n2_long, n2_lat), weight=w)
        elif file_extension == ".pkl":
            with open(self._graph_file, "rb") as f:
                loaded_graph = pickle.load(f)
                graph = loaded_graph.copy()

        if graph is None:
            raise Exception("Graph format invalid, no graph could be generated")
        return graph

    def find_closest_node(self, long_, lat_):
        """
        Finds the closest node in the world graph to a point of interest.

        Parameters
        ----------

        long_: float
            longitude of the point of interest
        lat_: float
            latitude of the point of interest

        Returns
        -------

        min_node: GraphX Node
            the node closest to those coordinates in the router's world_graph
        """
        #
        if (long_, lat_) in list(self.world_graph.nodes):
            return long_, lat_

        min_dist = float('inf')
        min_node = -1

        for node in list(self.world_graph.nodes):
            gg = LatLongShippingNetwork.get_long_lat_dist(lat_, long_, node[1], node[0])
            if gg <= min_dist:
                min_dist = gg
                min_node = node

        return min_node

    def create_canal_nodes(self):
        """
        Creates the canal nodes on the graph

        Returns
        -------

        nodes: {canal_name: (start_node, end_node)}
            dictionary containing the canal nodes

        """

        nodes = {}

        # find indices of canal entry and exit points in route
        for canal in self.canals.keys():
            # get closest nodes to entry and exit points of canals
            start_point, end_point = self.canals[canal]
            start_node = self.find_closest_node(start_point.longitude, start_point.latitude)
            end_node = self.find_closest_node(end_point.longitude, end_point.latitude)

            nodes[canal] = (start_node, end_node)

        return nodes

    def get_shortest_grid_route_between_points(self, start_long, start_lat, end_long, end_lat):
        """
        Calculates the shortest route between start longitude/latitude and end longitude/latitude using the grid graph

        Parameters
        ----------
        start_long: float
            The longitude of the start location.
        start_lat: float
            The latitude of the start location.
        end_long : float
            The longitude of the end location.
        end_lat : float
            The latitude of the end location.

        Returns
        -------
        [Tuple]
            List of (longitude, latitude) tuples that store the shortest route
        """
        # find the closest nodes in the world graph to the locations provided
        start_node = self.find_closest_node(start_long, start_lat)
        end_node = self.find_closest_node(end_long, end_lat)
        try:
            ship_path = networkx.shortest_path(self.world_graph, start_node, end_node, weight='weight')
        except networkx.exception.NetworkXNoPath:
            logger.error(
                "No path between " + str((start_long, start_lat)) + " and " + str((end_long, end_lat)) + " found.")
            raise NoPathsException(
                f"No paths between {repr(Location(start_long, start_lat))} and {repr(Location(end_long, end_lat))}")
        except Exception as ex:
            logger.error("Unknown error finding routes between " + str((start_long, start_lat)) + " and " + str(
                (end_long, end_lat)) + ". " + str(ex))
            raise NoPathsException(
                f"No paths between {repr(Location(start_long, start_lat))} and {repr(Location(end_long, end_lat))}")

        return ship_path

    def smooth_route(self, route, epsilon=1):
        """
        Smooths routes. If suez or panama entrances are found, simplify until them and from them.

        Parameters
        ----------

        route: [Tuple]
            List of (longitude, latitude) tuples that store the shortest route

        epsilon: float
            the epsilon value for the Ramer–Douglas–Peucker smoothing algorithm

        Returns
        -------

        [Tuple]
            Compressed list of (longitude, latitude) tuples that store the shortest route removing unnecessary points
        """

        canal_indexes = []
        final_route = []

        for canal_name, (start_node, end_node) in self.canals_nodes.items():
            # if a canal is found, add indexes
            if start_node in route and end_node in route:
                canal_indexes.append(route.index(start_node))
                canal_indexes.append(route.index(end_node))

        # if no canals were found, return direct simplified route
        if len(canal_indexes) == 0:
            return simplify_coords(route, epsilon)

        # add first and last indexes of the route
        canal_indexes.append(0)
        canal_indexes.append(len(route) - 1)

        # sort indexes array
        canal_indexes.sort()

        # create pairs of start - end positions for the nodes in each sub-route
        it = iter(canal_indexes)
        canal_indexes = [(x, next(it)) for x in it]

        final_routes = [route[s:e + 1] for s, e in canal_indexes]

        # smooth each individual sub-route
        for sub_route in final_routes:
            final_route.extend(simplify_coords(sub_route, epsilon))
        return final_route

    @staticmethod
    def compute_route_length(route):
        """
        Compute the length of a route by summing the distances between all of it's points.

        Parameters
        ----------
        route: [Tuple]
            List of (longitude, latitude) tuples that store the shortest route

        Returns
        -------

        float
            The length of the route in nautical miles
        """
        length = 0
        for pt_index in range(1, len(route)):
            lon_pt_start, lat_pt_start = route[pt_index - 1]
            lon_pt_end, lat_pt_end = route[pt_index]
            length += LatLongShippingNetwork.get_long_lat_dist(lat_pt_start, lon_pt_start, lat_pt_end, lon_pt_end)
        length_nautical_miles = round(length * 0.000539957, 2)
        return length_nautical_miles

    def get_shortest_route_between_points(self, start_long, start_lat, end_long, end_lat, smooth_path=True):
        """
        Calculates the shortest route between start longitude/latitude and end longitude/latitude.

        Parameters
        ----------
        start_long: float
            The longitude of the start location.
        start_lat: float
            The latitude of the start location.
        end_long : float
            The longitude of the end location.
        end_lat : float
            The latitude of the end location.
        smooth_path: boolean
            Flag to indicate whether or not to use smoothing algorithm on the path

        Returns
        -------
        [Tuple]
            List of (longitude, latitude) tuples that store the shortest route
        float
            The length of the route in nautical miles
        """
        ship_path = self.get_shortest_grid_route_between_points(start_long, start_lat, end_long, end_lat)
        # add in start and end points to generate total route
        route = [(start_long, start_lat)]
        route += ship_path
        route += [(end_long, end_lat)]
        if smooth_path:
            # since the smoothing algorithm transforms them into lists of lists, recast to tuples afterwards
            route = [tuple(pt) for pt in self.smooth_route(route)]
        length = self.compute_route_length(route)
        return route, length

    def create_world_canal_scenarios(self):
        """
        Creates a number of scenarios assuming different navigation canals are opened.

        Each scenario is a tuple containing an array of strings, each representing the name of a canal being considered.

        :return: List of canal names determining which canals are considered
        :rtype: List[Tuple[String]]
        """
        # iterate through different versions of the graph
        # one without the canals
        # one with each canal distinctly in the world graph
        # one with all canals in the world graph

        # array to store all scenarios
        canal_scenarios = []

        # create all possible combinations of canals being opened and closed
        for i in range(len(self.canals.keys()) + 1):
            canal_scenarios.extend(itertools.combinations(list(self.canals.keys()), i))

        return sorted(canal_scenarios, key=lambda e: len(e))

    def remove_canals_from_graph(self):
        """
        Removes all canal edges from the world graph.
        """

        # remove all canals initially
        for canal_key in self.canals_nodes.keys():
            start_node, end_node = self.canals_nodes[canal_key]

            if self.world_graph.has_edge(start_node, end_node):
                self.world_graph.remove_edge(start_node, end_node)

    def add_canal_to_graph(self, canal_name):
        """
        Adds a shipping canal to the world graph.

        Parameters
        ----------
        :param canal_name: string
            Name of the canal, also serves as key
        """

        start_node, end_node = self.canals_nodes[canal_name]

        # compute the distance
        weight = float(LatLongShippingNetwork.get_long_lat_dist(start_node[1], start_node[0], end_node[1], end_node[0]))

        # add the edge if not already present
        if not self.world_graph.has_edge(start_node, end_node):
            self.world_graph.add_edge(start_node, end_node, weight=weight)
        else:
            # TODO: discuss appropriate exception to be raised
            pass

    def compute_all_routes_between_points(self, start_location, end_location, vessel_type=None):
        """
        Computes a list of all routes between the locations.

        For the given start location and end location the direct route as well as the routes
        pass specified passage points (Suez (canal), Panama (canal)) are considered.

        Parameters
        ----------
        start_location: object (provides instance variables: longitude, latitude and name)
            The start location of the routes.
        end_location : object (provides instance variables: longitude, latitude and name)
            The end location of the routes.
        vessel_type: TODO
            TODO

        Returns
        -------
        [Route]
            List of all found routes.
        """

        start_long = start_location.longitude
        start_lat = start_location.latitude
        end_long = end_location.longitude
        end_lat = end_location.latitude

        # generate all paths from start to end location
        shortest_routes = set()

        # iterate through each scenario
        for scenario in self.scenarios:
            self.remove_canals_from_graph()

            # add canals to the world graph
            for canal in scenario:
                self.add_canal_to_graph(canal)

            # compute route and length in this scenario
            shortest_route, length_shortest_route = self.get_shortest_route_between_points(start_long, start_lat,
                                                                                           end_long, end_lat)

            new_route = Route("", shortest_route, length_shortest_route, scenario)
            if new_route not in shortest_routes:
                shortest_routes.add(new_route)

        shortest_routes = list(shortest_routes)

        if len(shortest_routes) > 0:
            shortest_routes = sorted(shortest_routes, key=lambda route: route.length)
        else:
            logger.error(f"No shortest paths from {(start_long, start_lat)} to {(end_long, end_lat)} found.")
            raise NoPathsException(
                f"No paths between {repr(Location(start_long, start_lat))} and {repr(Location(end_long, end_lat))}")

        return shortest_routes

    def get_all_routes_between_points(self, start_location, end_location, vessel_type=None):
        """
        Returns a list of all routes between the locations.

        For the given start location and end location the direct route as well as the routes
        pass specified passage points (Suez (canal), South Africa (Cape of Good Hope, Cape Agulhas),
        Panama (canal), Cape (North of Cape Horn), Singapore (Riau Islands south of Singapore Strait))
        are considered.

        Parameters
        ----------
        start_location: object (provides instance variables: longitude, latitude and name)
            The start location of the routes.
        end_location : object (provides instance variables: longitude, latitude and name)
            The end location of the routes.
        vessel_type: TODO
            TODO

        Returns
        -------
        [Route]
            List of all found routes.
        """
        if start_location == end_location:
            return [Route("", [], 0)]

        start_long = start_location.longitude
        start_lat = start_location.latitude
        end_long = end_location.longitude
        end_lat = end_location.latitude
        shortest_routes = self.get_all_stored_routes_between_points(start_location, end_location)

        # if routes are stored neither in the routing db nor the routing dictionary, 'manually' compute them
        if shortest_routes is None:
            logger.warning("No pre-computed shortest paths found. Computing paths for " + str(
                (start_long, start_lat)) + " to " + str((end_long, end_lat)))
            shortest_routes = self.compute_all_routes_between_points(start_location, end_location,
                                                                     vessel_type=vessel_type)
            index = f"{start_location.name}{end_location.name}"
            self._precomputed_routes[index] = shortest_routes
        return shortest_routes

    def get_all_stored_routes_between_points(self, start_location, end_location):
        """
        Returns the shortest routes stored.

        Parameters
        ----------
        start_location: object (provides instance variables: longitude, latitude and name)
            The start location of the routes.
        end_location : object (provides instance variables: longitude, latitude and name)
            The end location of the routes.

        Returns
        -------
        [Route] or None
            List of all found routes or None if no routes between locations has been stored before.
        """
        shortest_routes = None
        if self._precomputed_routes is not None:
            shortest_routes = self._get_precomputed_routes(start_location, end_location)
        return shortest_routes

    def get_shortest_path_between_points(self, start_location, end_location, vessel_type=None):
        """
        Returns the shortest route between the locations.

        Parameters
        ----------
        start_location: object (provides instance variables: longitude, latitude and name)
            The start location of the route.
        end_location : object (provides instance variables: longitude, latitude and name)
            The end location of the route.
        vessel_type: TODO
            TODO

        Returns
        -------
        Route
            The shortest route found.
        """
        paths = self.get_all_routes_between_points(start_location, end_location, vessel_type)
        # the paths are already sorted, just return the first one
        shortest_path = paths[0]
        return shortest_path


class Route:
    """
    Vessel route class.
    """

    def __init__(self, name, route, length, canal_nodes=None):
        """
        Constructor.

        Parameters
        ----------
        name : str
            Name of the route.
        route : [[float, float]]
            List of points of format [longitude, latitude].
        length : float
            The length of the route.
        canal_nodes: {canal_name: (start_node, end_node)}
            Stores all canals in the world with their start and end nodes in the graph
        """
        self.name = name
        self.route = route
        self.length = length
        self.canals = canal_nodes

    def __getitem__(self, item):
        """
        Legacy method to pretend a route is a tuple.

        Parameters
        ----------
        item : int
            Number from list index notation, e.g route[0].
        """

        if item == 0:
            return self.name
        elif item == 1:
            return self.route
        else:
            return self.length

    def __repr__(self):
        str_repr = ("Route<name: " + str(self.name)
                    + ", length: " + str(self.length)
                    + ", #stops: " + str(len(self.route)) + ">")
        return str_repr

    def __eq__(self, other):
        are_equal = False
        if isinstance(other, Route):
            if (self.name == other.name
                    and self.route == other.route
                    and self.length == other.length
                    and self.canals == other.canals):
                are_equal = True
        return are_equal

    def __hash__(self):
        return tuple([(pos[0], pos[1]) for pos in self.route]).__hash__()

    def as_tuple(self):
        return tuple([(pos[0], pos[1]) for pos in self.route])


class NoPathsException(Exception):
    pass
