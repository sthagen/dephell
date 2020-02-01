# built-in
from argparse import ArgumentParser

# app
from ..actions import make_json
from ..config import builders
from .base import BaseCommand


class InspectAuthCommand(BaseCommand):
    """Show saved credentials.
    """
    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_output(parser)
        return parser

    def __call__(self) -> bool:
        print(make_json(
            data=self.config['auth'],
            key=self.config.get('filter'),
            colors=not self.config['nocolors'],
            table=self.config['table'],
        ))
        return True
