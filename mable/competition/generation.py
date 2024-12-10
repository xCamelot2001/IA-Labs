import asyncio
import importlib.util
import pathlib
from pathlib import Path
from typing import TYPE_CHECKING
import sys

import loguru

from mable.cargo_bidding import TradingCompany
from mable.engine import SimulationEngine
from mable.event_management import CargoAnnouncementEvent, CargoEvent, FirstCargoAnnouncementEvent
from mable.extensions.cargo_distributions import DistributionShipping
from mable.extensions.fuel_emissions import FuelClassFactory, FuelSimulationFactory
from mable.shipping_market import AuctionMarket, StaticShipping, AuctionAllocationResult
from mable.simulation_de_serialisation import SimulationSpecification
import mable.instructions as instructions

if TYPE_CHECKING:
    from mable.shipping_market import AuctionLedger
    from mable.shipping_market import Trade


logger = loguru.logger


class AuctionSimulationEngine(SimulationEngine):

    def _set_up_trades(self):
        if isinstance(self.shipping, DistributionShipping):
            for one_time in self._shipping.get_trading_times():
                if one_time > 0:
                    if one_time == self.shipping.trade_occurrence_frequency:
                        if len(self.shipping.get_trades(0)) > 0:
                            one_announcement_event =  FirstCargoAnnouncementEvent(0, one_time)
                        else:
                            one_announcement_event = CargoAnnouncementEvent(0, one_time)
                    else:
                        announcement_time = one_time - self.shipping.trade_occurrence_frequency - 0.0000000001
                        one_announcement_event = CargoAnnouncementEvent(announcement_time, one_time)
                    self._world.event_queue.put(one_announcement_event)
        else:
            for one_time in self._shipping.get_trading_times():
                if one_time > 0:
                    if one_time == 30 * 24:
                        if len(self.shipping.get_trades(0)) > 0:
                            one_announcement_event =  FirstCargoAnnouncementEvent(0, one_time)
                        else:
                            one_announcement_event = CargoAnnouncementEvent(0, one_time)
                    else:
                        announcement_time = one_time - 30 * 24 - 0.0000000001
                        one_announcement_event = CargoAnnouncementEvent(announcement_time, one_time)
                    self._world.event_queue.put(one_announcement_event)


class AuctionCargoEvent(CargoEvent):
    """
    An event of appearance of cargoes in an auction setting.
    """

    def __init__(self, time):
        super().__init__(time)
        self._allocation_result: AuctionLedger | None = None

    @property
    def allocation_result(self):
        """
        The allocation result.

        :return:

        """
        return self._allocation_result

    def event_action(self, engine):
        """
        Collects the cargoes becoming available at the event's time from the shipping object and passes
        them to the market for distribution.

        :param engine: The simulation engine.
        :type engine: AuctionSimulationEngine
        :return: The distribution ledger.
        :rtype: AuctionLedger
        """
        engine.headquarters.get_companies()  # Update vessel locations before informing companies
        all_trades = engine.shipping.get_trades(self.time)
        distribution_ledger = engine.market.distribute_trades(
            self.time, all_trades, engine.shipping_companies, timeout=engine.global_agent_timeout)
        all_allocated_contracts_per_company = [distribution_ledger[k] for k in distribution_ledger.keys()]
        all_allocated_trades = [contract.trade
                                for on_company_trades in all_allocated_contracts_per_company
                                for contract in on_company_trades]
        unallocated_trades = [trade for trade in all_trades if trade not in all_allocated_trades]
        self._allocation_result = AuctionAllocationResult(distribution_ledger, unallocated_trades)
        num_awarded_trades = len(all_allocated_trades)
        self.info = f"Awarded {num_awarded_trades}/{len(all_trades)} trades"
        for current_company in engine.shipping_companies:
            asyncio.run(self._company_receive_timeout(
                current_company, distribution_ledger, timeout=engine.global_agent_timeout))
            engine.apply_new_schedules()
        return distribution_ledger

    @staticmethod
    async def _company_receive_timeout(company, distribution_ledger, timeout=60):
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    company.receive,
                    distribution_ledger.get_trades_for_company_copy(company),
                    distribution_ledger.sanitised_ledger),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Company {company.name} was stopped from operating 'receive' after {timeout} seconds.")


class AuctionClassFactory(FuelClassFactory):

    @staticmethod
    def generate_engine(*args, **kwargs):
        """
        Generates a simulation engine. Default: py:class:`maritime_simulator.engine.SimulationEngine`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The engine.
        """
        return AuctionSimulationEngine(*args, **kwargs)

    @staticmethod
    def generate_market(*args, **kwargs):
        """
        Generates a market. Default: py:class:`maritime_simulator.shipping_market.SimpleMarket`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The market.
        """
        return AuctionMarket(*args, **kwargs)

    @staticmethod
    def generate_event_cargo(*args, **kwargs):
        return AuctionCargoEvent(*args, **kwargs)

    @staticmethod
    def generate_shipping(*args, **kwargs):
        if "static" in kwargs:
            del kwargs["static"]
            return StaticShipping(*args, **kwargs)
        else:
            return FuelClassFactory.generate_shipping(*args, **kwargs)


class CompetitionBuilder(FuelSimulationFactory):

    def generate_shipping_companies(self, *args, **kwargs):
        """
        Generates the shipping companies including the vessels based on the specification information and the
        class factory's :py:func:`ClassFactory.generate_company` and :py:func:`SimulationFactory.generate_fleet`,
        respectively.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        shipping_company_instructions = self._specifications[instructions.COMPANIES_KEY]
        shipping_companies = []
        for one_company_instructions in shipping_company_instructions:
            one_company_args, one_company_kwargs = one_company_instructions[-1]
            one_company_args = one_company_args[0]
            class_name = one_company_args["current_class"]
            class_type = SimulationSpecification.get(class_name)
            schema = class_type.Data.Schema()
            company = schema.load(one_company_args)
            shipping_companies.append(company)
        self._companies = shipping_companies
        return self

    def set_engines(self, engine, *args, **kwargs):
        """
        Makes the engine known to the units constituting the simulation.
        """
        super().set_engines(engine, *args, **kwargs)
        objects_to_set = [one_arg for one_arg in args]
        for one_object in objects_to_set:
            if isinstance(one_object, TradingCompany):
                one_object.headquarters = engine.headquarters

    def generate_fleet(self, *args, **kwargs):
        """
        Generates the fleet of vessels of one company based on a list of vessel specifications and
        :py:func:`SimulationFactory.generate_vessel`.
        :param args:
            Positional args. The first argument should be a list of vessel instructions.
        :param kwargs:
            Keyword args.
        :return:
            A list of vessels.
        """
        fleet = []
        vessels = args[0]
        for one_vessel_arguments in vessels:
            one_vessel_schema_name = one_vessel_arguments["actual_type"]
            del one_vessel_arguments["actual_type"]
            one_vessel_schema = SimulationSpecification.get(one_vessel_schema_name)
            one_vessel = one_vessel_schema().loads(one_vessel_arguments)
            fleet.append(one_vessel)
        return fleet

def load_module_from_file(file_directory_path="."):
    # TODO test and finish
    all_group_files = pathlib.Path(file_directory_path).glob('group*.py')
    all_group_modules = []
    for one_group_file in all_group_files:
        file_path = Path(one_group_file)
        module_name = file_path.stem  # Use the file name (without extension) as the module name
        # Create a module spec
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            raise ImportError(f"Cannot find module in {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        all_group_modules.append(module)
    return all_group_modules
