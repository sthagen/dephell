# built-in
from argparse import REMAINDER, ArgumentParser

# app
from ..actions import make_json
from ..config import builders
from ..repositories import get_repo
from .base import BaseCommand


class PackageSearchCommand(BaseCommand):
    """Search packages on PyPI.org or Anaconda Cloud.
    """
    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_output(parser)
        builders.build_api(parser)
        builders.build_other(parser)
        parser.add_argument('name', nargs=REMAINDER, help='package name or other search keywords')
        return parser

    def __call__(self) -> bool:
        repo = get_repo(name=self.config.get('repo', 'pypi'))
        results = repo.search(self.args.name)
        if not results:
            self.logger.error('no results')
            return False
        print(make_json(
            data=results,
            key=self.config.get('filter'),
            colors=not self.config['nocolors'],
            table=self.config['table'],
        ))
        return True
