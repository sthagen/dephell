# built-in
from argparse import ArgumentParser

# external
from packaging.utils import canonicalize_name

# app
from ..actions import get_downloads_by_category, get_total_downloads, make_json
from ..config import builders
from .base import BaseCommand


class PackageDownloadsCommand(BaseCommand):
    """Show downloads statistic for package from PyPI.org.
    """
    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_output(parser)
        builders.build_api(parser)
        builders.build_other(parser)
        parser.add_argument('name', help='package name')
        return parser

    def __call__(self) -> bool:
        name = canonicalize_name(self.args.name)
        data = dict(
            total=get_total_downloads(name=name),
            pythons=get_downloads_by_category(category='pythons', name=name),
            systems=get_downloads_by_category(category='systems', name=name),
        )

        print(make_json(
            data=data,
            key=self.config.get('filter'),
            colors=not self.config['nocolors'],
            table=self.config['table'],
        ))
        return True
