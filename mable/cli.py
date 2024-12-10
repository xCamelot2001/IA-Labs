#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

import os
import sys
import json

import argparse as ap
import argcomplete
from loguru import logger
from prettytable import PrettyTable


class ArgumentParserExtensions:
    """
    Functions for use with the argument parser to parse arguments.
    """

    @staticmethod
    def is_valid_file(filename, parser):
        """
        An ArgumentParser argument to check if the provided file name corresponds to an existing file.

        :param filename:
            The file name.
        :type filename: str
        :param parser:
            The calling sub-parser for an error call if necessary.
        :return:
            The file name if the file exists. Otherwise, will exit via a parser error.
        :rtype: str
        """
        if not os.path.isfile(filename):
            parser.error(f"File {filename} does not exist.")
        return filename

    @staticmethod
    def is_positive_integer(value, parser):
        """
        An ArgumentParser argument to check if the provided value is a positive integer.

        :param value:
            The value.
        :type value: str
        :param parser:
            The calling sub-parser for an error call if necessary.
        :return:
            The int value if it is a positive int. Otherwise, will exit via a parser error.
        :rtype: int
        """
        try:
            value = int(value)
        except ValueError:
            parser.error(f"The input {value} is not an integer.")
        if value <= 0:
            parser.error(f"The input {value} is not a positive integer.")
        return value


def task_metrics_overview(parsed_args):
    """
    Generate an overview of the companies' performance.

    :param parsed_args:
        The parameter from the arg parser.
        - file: str: the name of the file.
    :type parsed_args: dict
    """
    metrics_file_name = parsed_args["file"]
    print(f"Overview for {metrics_file_name}.")
    with open(metrics_file_name, "r") as f:
        metrics = json.load(f)
    for one_company_key in metrics["company_metrics"]:
        company_name = metrics["company_names"][one_company_key]
        print(f"Company {company_name}")
        cost = 0
        if "fuel_cost" in metrics["company_metrics"][one_company_key]:
            cost = metrics["company_metrics"][one_company_key]["fuel_cost"]
        penalty = metrics["global_metrics"]["penalty"][one_company_key]
        revenue = 0
        all_outcomes = metrics["global_metrics"]["auction_outcomes"]
        all_outcomes_company_per_round = [d[one_company_key] for d in all_outcomes if one_company_key in d]
        all_outcomes_company = [x for sublist in all_outcomes_company_per_round for x in sublist]
        all_payments = [d["payment"] for d in all_outcomes_company]
        revenue += sum(all_payments)
        income = revenue - cost - penalty
        table = PrettyTable()
        table.field_names = ["Name", "Value"]
        table.align["Value"] = "r"
        table.add_row(["Cost", round(cost, 3)])
        table.add_row(["Penalty", round(penalty, 3)])
        table.add_row(["Revenue", round(revenue, 3)], divider=True)
        table.add_row(["Income", round(income, 3)])
        print(table)


def select_task(parsed_args):
    """
    Calls the respective function for the task as specified by the cmd args.

    :param parsed_args:dict
        The parameter from the arg parser.
    """
    task = parsed_args["task"]
    if task == "overview":
        task_metrics_overview(parsed_args)
    else:
        logger.error(f"Unknown task {task}")


def main():
    """
    Main entry of program. Set arguments for argument parser, loads the settings and
    searches current directory for compilable tex files. At the end prints help or calls
    the task selector function to perform one of the tasks.
    """
    parser = ap.ArgumentParser()
    # Reusable arguments
    parent_force_action = ap.ArgumentParser(add_help=False)
    parent_force_action.add_argument("-f",
                                     action="store_true",
                                     help="Force action "
                                          + "(do not ask for confirmation when overwriting or deleting files).")
    verbose_print = ap.ArgumentParser(add_help=False)
    verbose_print.add_argument('-v', '--verbose', action="store_const", const=True, default=False,
                               help="Activate verbose mode.")
    # Parsers for tasks
    task_parsers = parser.add_subparsers(dest='task')
    # Overview
    overview_parser = task_parsers.add_parser(
        'overview',
        parents=[],
        help='Show an overview of a run simulation.'
    )
    overview_parser.add_argument(
        'file',
        type=lambda x: ArgumentParserExtensions.is_valid_file(x, overview_parser),
        help="Filename for which to produce the overview."
    )
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    args = vars(args)
    if args["task"] is not None:
        select_task(args)
    else:
        parser.print_help()


def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Log any exception which is not a KeyboardInterrupt.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:
        logger.error(f"Uncaught exception: type '{exc_type}', value '{exc_value}'")


sys.excepthook = handle_exception


if __name__ == '__main__':
    main()
