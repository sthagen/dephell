# built-in
from collections import defaultdict
from email.parser import Parser
from itertools import chain
from pathlib import Path
from typing import Dict, Optional

# external
from dephell_discover import Root as PackageRoot
from dephell_links import parse_link
from dephell_markers import Markers
from packaging.requirements import Requirement as PackagingRequirement

# app
from ..constants import DOWNLOAD_FIELD, HOMEPAGE_FIELD
from ..controllers import DependencyMaker, Readme
from ..models import Author, EntryPoint, RootDependency
from .base import BaseConverter
from .setuppy import SetupPyConverter


class _Reader:

    def can_parse(self, path: Path, content: Optional[str] = None) -> bool:
        if isinstance(path, str):
            path = Path(path)
        if path.suffix == '.egg-info':
            return True
        if path.name in ('requires.txt', 'PKG-INFO'):
            return True
        return False

    def load(self, path) -> RootDependency:
        path = Path(str(path))
        if path.is_dir():
            # load from *.egg-info dir
            if (path / 'PKG-INFO').exists():
                return self.load_dir(path)
            # find *.egg-info in current dir
            paths = list(path.glob('*.egg-info'))
            return self.load_dir(*paths)

        if path.suffix in ('.zip', '.gz', '.tar'):
            raise ValueError('Please, use SDistConverter for archives')

        if path.suffix == '.whl':
            raise ValueError('Please, use WheelConverter for *.whl archives')

        # load from file (requires.txt or PKG-INFO)
        with path.open('r', encoding='utf-8') as stream:
            return self.loads(stream.read())

    def load_dir(self, *paths) -> RootDependency:
        # drop duplicates
        paths = list({str(path): path for path in paths}.values())
        if not paths:
            raise FileNotFoundError('cannot find egg-info')
        # maybe it's possible, so we will have to process it
        if len(paths) > 1:
            min_parts = min(len(path.parts) for path in paths)
            paths = [path for path in paths if len(path.parts) == min_parts]
            if len(paths) > 1:
                raise FileExistsError('too many egg-info', paths)
        path = paths[0]

        # sometimes pypy stores only pkg-info as *.egg-info file
        if not (path / 'PKG-INFO').exists():
            with path.open('r') as stream:
                content = stream.read()
            return self.parse_info(content)

        # dependency_links.txt
        urls = dict()
        if (path / 'dependency_links.txt').exists():
            with (path / 'dependency_links.txt').open('r') as stream:
                content = stream.read()
            urls = self.parse_dependency_links(content)

        # pkg-info
        with (path / 'PKG-INFO').open('r') as stream:
            content = stream.read()
        root = self.parse_info(content, urls=urls)

        # requires.txt
        if not root.dependencies and (path / 'requires.txt').exists():
            with (path / 'requires.txt').open('r') as stream:
                content = stream.read()
            root = self.parse_requires(content, root=root, urls=urls)

        # entry_points.txt
        if (path / 'entry_points.txt').exists():
            with (path / 'entry_points.txt').open('r') as stream:
                content = stream.read()
            root = self.parse_entrypoints(content, root=root)

        # readme and package files
        root.readme = Readme.discover(path=path)
        root.package = PackageRoot(
            path=self.project_path or path.parent,
            name=root.name,
        )
        return root

    def loads(self, content: str) -> RootDependency:
        if 'Name: ' in content:
            return self.parse_info(content=content)
        elif '[console_scripts] ' in content:
            return self.parse_entrypoints(content=content)
        else:
            return self.parse_requires(content=content)

    @classmethod
    def parse_info(cls, content: str, root=None, urls: Dict[str, str] = None) -> RootDependency:
        if urls is None:
            urls = dict()

        info = Parser().parsestr(content)
        root = RootDependency(
            raw_name=cls._get(info, 'Name'),
            version=cls._get(info, 'Version') or '0.0.0',

            description=cls._get(info, 'Summary'),
            license=cls._get(info, 'License'),

            keywords=cls._get(info, 'Keywords').split(','),
            classifiers=cls._get_list(info, 'Classifier'),
            platforms=cls._get_list(info, 'Platform'),
        )

        # links
        fields = (
            (HOMEPAGE_FIELD, 'Home-Page'),
            (DOWNLOAD_FIELD, 'Download-URL'),
        )
        for key, name in fields:
            link = cls._get(info, name)
            if link:
                root.links[key] = link
        for link in cls._get_list(info, 'Project-URL'):
            key, url = link.split(', ')
            root.links[key.lower()] = url

        # authors
        for name in ('author', 'maintainer'):
            author = cls._get(info, name)
            if author:
                root.authors += (
                    Author(name=author, mail=cls._get(info, name + '_email')),
                )

        # dependencies
        deps = []
        for req in cls._get_list(info, 'Requires-Dist'):
            req = PackagingRequirement(req)
            deps.extend(DependencyMaker.from_requirement(
                source=root,
                req=req,
                url=urls.get(req.name),
            ))
        root.attach_dependencies(deps)
        return root

    def parse_requires(self, content: str, root=None, urls: Dict[str, str] = None) -> RootDependency:
        if urls is None:
            urls = dict()
        if root is None:
            root = RootDependency()

        envs = {'main'}
        marker = Markers()
        for req in content.split('\n'):
            req = req.strip()
            if not req or req[0] in '#;':
                continue
            # get section name as extra
            if req[0] == '[' and req[-1] == ']':
                extra, marker = self._split_extra_and_marker(req)
                envs = {extra} if extra == 'dev' else {'main', extra}
                continue

            req = PackagingRequirement(req)
            deps = DependencyMaker.from_requirement(
                source=root,
                req=req,
                envs=envs,
                marker=marker,
                url=urls.get(req.name),
            )
            root.attach_dependencies(deps)
        return root

    def parse_entrypoints(self, content: str, root=None) -> RootDependency:
        if root is None:
            root = RootDependency()
        entrypoints = []
        group = 'console_scripts'
        for line in content.split('\n'):
            line = line.strip()
            if not line or line[0] in '#;':  # ignore comments
                continue
            if line[0] == '[' and line[-1] == ']':
                group = line[1:-1]
            else:
                entrypoints.append(EntryPoint.parse(text=line, group=group))
        root.entrypoints = tuple(entrypoints)
        return root

    def parse_dependency_links(self, content: str) -> Dict[str, str]:
        urls = dict()
        for url in content.split('\n'):
            url = url.strip()
            if not url or url[0] == '#':
                continue
            parsed = parse_link(url)
            name = parsed.name.split('-')[0]
            urls[name] = url
        return urls

    @staticmethod
    def _get(msg, name: str) -> str:
        value = msg.get(name)
        if not value:
            return ''
        value = value.strip()
        if value == 'UNKNOWN':
            return ''
        return value

    @staticmethod
    def _get_list(msg, name: str) -> tuple:
        values = msg.get_all(name)
        if not values:
            return ()
        return tuple(value.strip() for value in values if value.strip() != 'UNKNOWN')


# https://setuptools.readthedocs.io/en/latest/formats.html
class _Writer:
    def dump(self, reqs, path: Path, project: RootDependency) -> None:
        if isinstance(path, str):
            path = Path(path)

        if path.is_file():
            path.write_text(self.make_info(reqs=reqs, project=project, with_requires=False))
            return

        if path.suffix != '.egg-info':
            path /= project.raw_name.replace('-', '_') + '.egg-info'
        path.mkdir(exist_ok=True, parents=True)

        (path / 'dependency_links.txt').write_text(self.make_dependency_links(reqs=reqs))
        (path / 'entry_points.txt').write_text(self.make_entrypoints(project=project))
        (path / 'PKG-INFO').write_text(self.make_info(reqs=reqs, project=project, with_requires=False),
                                       encoding='utf8')
        (path / 'requires.txt').write_text(self.make_requires(reqs=reqs))
        (path / 'SOURCES.txt').write_text(self.make_sources(project=project))
        (path / 'top_level.txt').write_text(self.make_top_level(project=project))

    def dumps(self, reqs, project: RootDependency, content: Optional[str] = None) -> str:
        return self.make_info(reqs=reqs, project=project, with_requires=True)

    def make_info(self, reqs, project: RootDependency, with_requires: bool) -> str:
        # distutils.dist.DistributionMetadata.write_pkg_file
        content = []
        content.append(('Metadata-Version', '2.1'))
        content.append(('Name', project.raw_name.replace('_', '-')))
        content.append(('Version', project.version))
        if project.description:
            content.append(('Summary', project.description))

        # links
        for key, url in project.links.items():
            key = key[0].upper() + key[1:]
            content.append(('Project-URL', '{}, {}'.format(key, url)))

        # authors
        if project.authors:
            author = project.authors[0]
            content.append(('Author', author.name))
            if author.mail:
                content.append(('Author-email', author.mail))
        if len(project.authors) > 1:
            author = project.authors[1]
            content.append(('Maintainer', author.name))
            if author.mail:
                content.append(('Maintainer-email', author.mail))

        if project.license:
            content.append(('License', project.license))
        if project.python:
            content.append(('Requires-Python', str(project.python.peppify())))
        if project.keywords:
            content.append(('Keywords', ','.join(project.keywords)))
        for classifier in project.classifiers:
            content.append(('Classifier', classifier))
        for platform in project.platforms:
            content.append(('Platform', platform))
        if with_requires:
            for req in reqs:
                content.append(('Requires-Dist', self._format_req(req=req, with_envs=True)))

        extras = set()
        for req in reqs:
            extras.update(req.main_envs)  # all envs (including dev and excluding main)
        for extra in sorted(extras):
            content.append(('Provides-Extra', extra))

        content = '\n'.join(map(': '.join, content))
        if project.readme:
            content += '\n\n' + project.readme.as_rst()
        return content

    def make_requires(self, reqs) -> str:
        content = []
        extras = defaultdict(list)
        for req in reqs:
            if req.main_envs:
                for env in req.main_envs:
                    extras[env].append(req)
            else:
                content.append(self._format_req(req=req, with_envs=False))

        # write extra deps
        for extra, reqs in sorted(extras.items()):
            content.append('\n[{}]'.format(extra))
            for req in reqs:
                content.append(self._format_req(req=req, with_envs=False))

        return '\n'.join(content)

    def make_dependency_links(self, reqs) -> str:
        content = []
        for req in reqs:
            if req.link is not None:
                content.append(SetupPyConverter._format_link(req=req))
        return '\n'.join(content)

    @staticmethod
    def make_entrypoints(project: RootDependency) -> str:
        points = defaultdict(set)
        for point in project.entrypoints:
            points[point.group].add(str(point))
        content = []
        for group, subpoints in sorted(points.items()):
            content.append('\n[{}]'.format(group))
            content.extend(sorted(subpoints))
        return '\n'.join(content).strip()

    @staticmethod
    def make_sources(project: RootDependency) -> str:
        content = []
        if project.readme:
            content.append(project.readme.path.name)
            if project.readme.markup != 'rst':
                content.append(project.readme.to_rst().path.name)

        path = project.package.path
        for fname in ('setup.cfg', 'setup.py'):
            if (path / fname).exists():
                content.append(fname)

        for package in chain(project.package.packages, project.package.data):
            for fpath in package:
                fpath = fpath.relative_to(project.package.path)
                content.append('/'.join(fpath.parts))

        return '\n'.join(content)

    @staticmethod
    def make_top_level(project: RootDependency) -> str:
        content = {p.module.split('.', maxsplit=1)[0] for p in project.package.packages}
        return '\n'.join(sorted(content))

    @staticmethod
    def _format_req(req, with_envs: bool) -> str:
        line = req.raw_name
        if req.extras:
            line += '[{extras}]'.format(extras=','.join(req.extras))
        if req.version:
            line += req.version

        markers = None
        if req.markers:
            markers = Markers(req.markers)
        if with_envs and req.main_envs:
            env_markers = Markers(' or '.join('extra == "{}"'.format(env) for env in req.main_envs))
            markers = markers & env_markers if markers else env_markers
        if markers:
            line += '; ' + str(markers)

        return line


class EggInfoConverter(_Reader, _Writer, BaseConverter):
    """
    PEP-314, PEP-345, PEP-566
    https://packaging.python.org/specifications/core-metadata/
    """
    lock = False
