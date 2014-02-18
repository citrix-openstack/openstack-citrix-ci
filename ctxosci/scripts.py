import argparse
from ctxosci import commands


def get_parser_for(command):
    parser = argparse.ArgumentParser()
    for parameter in command.parameters():
        parser.add_argument(parameter)

    return parser


def get_dom0_logs():
    command_class = commands.GetDom0Logs
    parser = get_parser_for(command_class)
    env = parser.parse_args()
    command = command_class(vars(env))
    command()
