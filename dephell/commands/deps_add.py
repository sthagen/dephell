
# built-in
from argparse import ArgumentParser
from pathlib import Path

# app
from ..actions import get_resolver
from ..config import builders
from ..controllers import analyze_conflict
from ..converters import CONVERTERS
from ..models import Requirement
from .base import BaseCommand


class DepsAddCommand(BaseCommand):
    """Add new packages into project dependencies.
    """
    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_from(parser)
        builders.build_resolver(parser)
        builders.build_output(parser)
        builders.build_api(parser)
        builders.build_other(parser)
        parser.add_argument('name', nargs='+', help='packagess names and versions')
        return parser

    def __call__(self) -> bool:
        # get current deps
        if 'from' not in self.config:
            self.logger.error('`--from` is required for this command')
            return False
        converter = CONVERTERS[self.config['from']['format']]
        converter = converter.copy(project_path=Path(self.config['project']))
        resolver = converter.load_resolver(path=self.config['from']['path'])

        # get new deps
        new_resolver = get_resolver(reqs=self.args.name)
        new_root = new_resolver.graph._roots[0]
        new_root.name = 'new-root'

        # set envs
        for dep in new_root.dependencies:
            dep.envs = set(self.config.get('envs', {'main'}))

        # mix them up
        self.logger.debug('merge...')
        resolver.graph.add(new_root)
        resolved = resolver.resolve(level=1, silent=self.config['silent'])
        if not resolved:
            conflict = analyze_conflict(resolver=resolver)
            self.logger.warning('conflict was found')
            print(conflict)
            return False

        # write merged deps back
        self.logger.debug('dump dependencies...')
        converter.dump(
            path=self.config['from']['path'],
            reqs=Requirement.from_graph(resolver.graph, lock=converter.lock),
            project=resolver.graph.metainfo,
        )

        self.logger.info('added')
        return True
