# built-in
import asyncio
import html
import posixpath
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urljoin, urlparse

# external
import attr
from dephell_specifier import RangeSpecifier
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

# app
from ...cache import JSONCache, TextCache
from ...config import config
from ...constants import ARCHIVE_EXTENSIONS
from ...exceptions import PackageNotFoundError
from ...imports import lazy_import
from ...models.release import Release
from ...networking import requests_session
from ._base import WarehouseBaseRepo


html5lib = lazy_import('html5lib')
logger = getLogger('dephell.repositories.warehouse.simple')


@attr.s()
class WarehouseSimpleRepo(WarehouseBaseRepo):
    name = attr.ib(type=str)
    url = attr.ib(type=str)
    pretty_url = attr.ib(type=str, default='')
    auth = attr.ib(default=None)

    prereleases = attr.ib(type=bool, factory=lambda: config['prereleases'])  # allow prereleases
    from_config = attr.ib(type=bool, default=False)
    propagate = True  # deps of deps will inherit repo

    def __attrs_post_init__(self):
        # make name canonical
        if self.name in ('pypi.org', 'pypi.python.org'):
            self.name = 'pypi'
        if not self.pretty_url:
            self.pretty_url = self.url
        self.url = self._get_url(self.url, default_path='/simple/')

    def get_releases(self, dep) -> tuple:
        links = self._get_links(name=dep.base_name)
        releases_info = dict()
        for link in links:
            name, version = self._parse_name(link['name'])
            if canonicalize_name(name) != canonicalize_name(dep.base_name):
                logger.warning('bad dist name', extra=dict(
                    dist_name=link['name'],
                    package_name=dep.base_name,
                    reason='package name does not match',
                ))
                continue
            if not version:
                logger.warning('bad dist name', extra=dict(
                    dist_name=link['name'],
                    package_name=dep.base_name,
                    reason='no version specified',
                ))
                continue

            if version not in releases_info:
                releases_info[version] = dict(hashes=[], pythons=[])
            if link['digest']:
                releases_info[version]['hashes'].append(link['digest'])
            if link['python']:
                releases_info[version]['pythons'].append(link['python'])

        # init releases
        releases = []
        prereleases = []
        for version, info in releases_info.items():
            # ignore version if no files for release
            release = Release(
                raw_name=dep.raw_name,
                version=version,
                time=datetime(1970, 1, 1, 0, 0),
                python=RangeSpecifier(' || '.join(info['pythons'])),
                hashes=tuple(info['hashes']),
                extra=dep.extra,
            )

            # filter prereleases if needed
            if release.version.is_prerelease:
                prereleases.append(release)
                if not self.prereleases and not dep.prereleases:
                    continue

            releases.append(release)

        # special case for black: if there is no releases, but found some
        # prereleases, implicitly allow prereleases for this package
        if not releases and prereleases:
            releases = prereleases

        releases.sort(reverse=True)
        return tuple(releases)

    async def get_dependencies(self, name: str, version: str,
                               extra: Optional[str] = None) -> Tuple[Requirement, ...]:
        cache = TextCache('warehouse-simple', urlparse(self.url).hostname, 'deps', name, str(version))
        deps = cache.load()
        if deps is None:
            task = self._get_deps_from_links(name=name, version=version)
            deps = await asyncio.gather(asyncio.ensure_future(task))
            deps = deps[0]
            cache.dump(deps)
        elif deps == ['']:
            return ()
        return self._convert_deps(deps=deps, name=name, version=version, extra=extra)

    def search(self, query: Iterable[str]) -> List[Dict[str, str]]:
        raise NotImplementedError

    async def download(self, name: str, version: str, path: Path) -> bool:
        if not isinstance(version, str):
            version = str(version)

        links = self._get_links(name=name)
        good_links = []
        for link in links:
            link_name, link_version = self._parse_name(link['name'])
            if canonicalize_name(link_name) != name:
                continue
            if link_version != version:
                continue
            good_links.append(link)

        exts = ('py3-none-any.whl', '-none-any.whl', '.whl', '.tar.gz', '.zip')
        for ext in exts:
            for link in good_links:
                if not link['name'].endswith(ext):
                    continue
                if path.is_dir():
                    fname = urlparse(link['url']).path.strip('/').rsplit('/', maxsplit=1)[-1]
                    path = path / fname
                await self._download(url=link['url'], path=path)
                return True
        return False

    # private methods

    def _get_links(self, name: str) -> List[Dict[str, str]]:
        cache = JSONCache(
            'warehouse-simple', urlparse(self.url).hostname, 'links', name,
            ttl=config['cache']['ttl'],
        )
        links = cache.load()
        if links is not None:
            yield from links
            return

        dep_url = posixpath.join(self.url, quote(name)) + '/'
        with requests_session() as session:
            logger.debug('getting dep info from simple repo', extra=dict(url=dep_url))
            response = session.get(dep_url, auth=self.auth)
        if response.status_code == 404:
            raise PackageNotFoundError(package=name, url=dep_url)
        response.raise_for_status()
        document = html5lib.parse(response.text, namespaceHTMLElements=False)

        links = []
        for tag in document.findall('.//a'):
            link = tag.get('href')
            if not link:
                continue
            parsed = urlparse(link)
            if not parsed.path.endswith(ARCHIVE_EXTENSIONS):
                continue

            python = tag.get('data-requires-python')
            fragment = parse_qs(parsed.fragment)
            link = dict(
                url=urljoin(dep_url, link),
                name=parsed.path.strip('/').split('/')[-1],
                python=html.unescape(python) if python else '*',
                digest=fragment['sha256'][0] if 'sha256' in fragment else None,
            )
            links.append(link)
            yield link

        cache.dump(links)
        return links

    async def _get_deps_from_links(self, name: str, version):
        from ...converters import SDistConverter, WheelConverter

        links = self._get_links(name=name)
        good_links = []
        for link in links:
            link_name, link_version = self._parse_name(link['name'])
            if canonicalize_name(link_name) != name:
                continue
            if link_version != str(version):
                continue
            good_links.append(link)

        sdist = SDistConverter()
        wheel = WheelConverter()
        rules = (
            (wheel, 'py3-none-any.whl'),
            (wheel, '-none-any.whl'),
            (wheel, '.whl'),
            (sdist, '.tar.gz'),
            (sdist, '.zip'),
        )

        for converter, ext in rules:
            for link in good_links:
                if not link['name'].endswith(ext):
                    continue
                try:
                    return await self._download_and_parse(
                        url=link['url'],
                        converter=converter,
                    )
                except FileNotFoundError as e:
                    logger.warning(e.args[0])
        return ()
