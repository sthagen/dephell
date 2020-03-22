# built-in
from collections import defaultdict
from json import dumps as json_dumps
from logging import getLogger
from pathlib import Path
from typing import Optional

# external
from dephell_discover import Root as PackageRoot
from dephell_links import DirLink, FileLink, URLLink, VCSLink, parse_link
from dephell_setuptools import read_setup
from dephell_specifier import RangeSpecifier
from packaging.requirements import Requirement

# app
from ..constants import DOWNLOAD_FIELD, HOMEPAGE_FIELD
from ..controllers import DependencyMaker, Readme
from ..models import Author, EntryPoint, RootDependency
from .base import BaseConverter


try:
    from yapf.yapflib.style import CreateGoogleStyle
    from yapf.yapflib.yapf_api import FormatCode
except ImportError:
    FormatCode = None
try:
    from autopep8 import fix_code
except ImportError:
    fix_code = None


logger = getLogger('dephell.converters.setuppy')


TEMPLATE = """
# -*- coding: utf-8 -*-

# DO NOT EDIT THIS FILE!
# This file has been autogenerated by dephell <3
# https://github.com/dephell/dephell

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

{readme}

setup(
    long_description=readme,
    {kwargs},
)
"""


class SetupPyConverter(BaseConverter):
    lock = False

    def can_parse(self, path: Path, content: Optional[str] = None) -> bool:
        if isinstance(path, str):
            path = Path(path)
        if path.name == 'setup.py':
            return True
        if not content:
            return False
        if 'setuptools' not in content and 'distutils' not in content:
            return False
        return ('setup(' in content)

    def load(self, path) -> RootDependency:
        if isinstance(path, str):
            path = Path(path)
        path = self._make_source_path_absolute(path)
        self._resolve_path = path.parent

        data = read_setup(path=path, error_handler=logger.debug)
        root = RootDependency(
            raw_name=data['name'],
            version=data.get('version', '0.0.0'),
            package=PackageRoot(
                path=self.project_path or Path(),
                name=data['name'],
            ),

            description=data.get('description'),
            license=data.get('license'),

            keywords=tuple(data.get('keywords', ())),
            classifiers=tuple(data.get('classifiers', ())),
            platforms=tuple(data.get('platforms', ())),

            python=RangeSpecifier(data.get('python_requires')),
            readme=Readme.from_code(path=path),
        )

        # links
        fields = (
            (HOMEPAGE_FIELD, 'url'),
            (DOWNLOAD_FIELD, 'download_url'),
        )
        for key, name in fields:
            link = data.get(name)
            if link:
                root.links[key] = link

        # authors
        for name in ('author', 'maintainer'):
            author = data.get(name)
            if author:
                root.authors += (
                    Author(name=author, mail=data.get(name + '_email')),
                )

        # entrypoints
        entrypoints = []
        for group, content in data.get('entry_points', {}).items():
            for entrypoint in content:
                entrypoints.append(EntryPoint.parse(text=entrypoint, group=group))
        root.entrypoints = tuple(entrypoints)

        # dependency_links
        urls = dict()
        for url in data.get('dependency_links', ()):
            parsed = parse_link(url)
            name = parsed.name.split('-')[0]
            urls[name] = url

        # dependencies
        for req in data.get('install_requires', ()):
            req = Requirement(req)
            root.attach_dependencies(DependencyMaker.from_requirement(
                source=root,
                req=req,
                url=urls.get(req.name),
            ))

        # extras
        for extra, reqs in data.get('extras_require', {}).items():
            extra, marker = self._split_extra_and_marker(extra)
            envs = {extra} if extra == 'dev' else {'main', extra}
            for req in reqs:
                req = Requirement(req)
                root.attach_dependencies(DependencyMaker.from_requirement(
                    source=root,
                    req=req,
                    marker=marker,
                    envs=envs,
                ))

        return root

    def dumps(self, reqs, project: RootDependency, content=None) -> str:
        """
        https://setuptools.readthedocs.io/en/latest/setuptools.html#metadata
        """
        content = []
        content.append(('name', project.raw_name))
        content.append(('version', project.version))
        if project.description:
            content.append(('description', project.description))
        if project.python:
            content.append(('python_requires', str(project.python.peppify())))

        # links
        if project.links:
            content.append(('project_urls', project.links))

        # authors
        if project.authors:
            author = project.authors[0]
            content.append(('author', author.name))
            if author.mail:
                content.append(('author_email', author.mail))
        if len(project.authors) > 1:
            author = project.authors[1]
            content.append(('maintainer', author.name))
            if author.mail:
                content.append(('maintainer_email', author.mail))

        if project.license:
            content.append(('license', project.license))
        if project.keywords:
            content.append(('keywords', ' '.join(project.keywords)))
        if project.classifiers:
            content.append(('classifiers', list(project.classifiers)))
        if project.platforms:
            content.append(('platforms', project.platforms))
        if project.entrypoints:
            entrypoints = defaultdict(list)
            for entrypoint in project.entrypoints:
                entrypoints[entrypoint.group].append(str(entrypoint))
            content.append(('entry_points', entrypoints))

        # packages, package_data
        content.append(('packages', sorted(str(p) for p in project.package.packages)))
        if project.package.package_dir:
            content.append(('package_dir', project.package.package_dir))
        data = defaultdict(list)
        for rule in project.package.data:
            data[rule.module].append(rule.relative)
        data = {package: sorted(paths) for package, paths in data.items()}
        content.append(('package_data', data))

        # depedencies
        reqs_list = [self._format_req(req=req) for req in reqs if not req.main_envs]
        content.append(('install_requires', reqs_list))

        # dependency_links
        links = []
        for req in reqs:
            if req.dep.link is not None:
                links.append(self._format_link(req=req))
        if links:
            content.append(('dependency_links', links))

        # extras
        extras = defaultdict(list)
        for req in reqs:
            if req.main_envs:
                formatted = self._format_req(req=req)
                for env in req.main_envs:
                    extras[env].append(formatted)
        if extras:
            content.append(('extras_require', extras))

        if project.readme is not None:
            readme = project.readme.to_rst().as_code()
        else:
            readme = "readme = ''"

        content = ',\n    '.join(
            '{}={!s}'.format(name, json_dumps(value, sort_keys=True))
            if isinstance(value, dict) else '{}={!r}'.format(name, value)
            for name, value in content)
        content = TEMPLATE.format(kwargs=content, readme=readme)

        # beautify
        if FormatCode is not None:
            content, _changed = FormatCode(content, style_config=CreateGoogleStyle())
        if fix_code is not None:
            content = fix_code(content)

        return content

    # private methods

    @staticmethod
    def _format_req(req) -> str:
        line = req.raw_name
        if req.extras:
            line += '[{extras}]'.format(extras=','.join(req.extras))
        if req.version:
            line += req.version
        if req.markers:
            line += '; ' + req.markers
        return line

    @staticmethod
    def _format_link(req) -> str:
        link = req.dep.link
        egg = '#egg=' + req.name
        if req.release:
            egg += '-' + str(req.release.version)

        if isinstance(link, (FileLink, DirLink)):
            return link.short

        if isinstance(link, VCSLink):
            result = link.vcs + '+' + link.short
            if link.rev:
                result += '@' + link.rev
            return result + egg

        if isinstance(link, URLLink):
            return link.short + egg

        raise ValueError('invalid link for {}'.format(req.name))
