import sys
import argparse
import logging
from ctxosci import commands


def get_parser_for(command):
    parser = argparse.ArgumentParser()
    for parameter in command.parameters():
        parser.add_argument(parameter)

    return parser


def setup_logging():
    logging.basicConfig(level=logging.DEBUG)


def cp_dom0_logserver():
    setup_logging()
    command_class = commands.GetDom0Logs
    parser = get_parser_for(command_class)
    env = parser.parse_args()
    command = command_class(vars(env))
    command()


def check_connection():
    setup_logging()
    command_class = commands.CheckConnection
    parser = get_parser_for(command_class)
    env = parser.parse_args()
    command = command_class(vars(env))
    sys.exit(command())
