# built-in
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Type, Union
from urllib.parse import urljoin, urlparse

# external
import attr
import requests
from requests.exceptions import ConnectionError, SSLError

# app
from ..config import config as global_config
from ..constants import WAREHOUSE_DOMAINS
from ..exceptions import PackageNotFoundError
from ..models import Auth
from ..repositories import WarehouseAPIRepo, WarehouseBaseRepo, WarehouseLocalRepo, WarehouseSimpleRepo


@lru_cache(maxsize=16)
def _has_api(url: str) -> bool:
    if urlparse(url).hostname in ('pypi.org', 'python.org', 'test.pypi.org'):
        return True
    full_url = urljoin(url, 'dephell/json/')
    try:
        response = requests.head(full_url)
    except (SSLError, ConnectionError):
        return False
    return response.status_code < 400


@attr.s()
class RepositoriesRegistry(WarehouseBaseRepo):
    repos: List[WarehouseBaseRepo] = attr.ib(factory=list)
    prereleases = attr.ib(type=bool, factory=lambda: global_config['prereleases'])  # allow prereleases
    from_config = attr.ib(type=bool, default=False)

    _urls: Set[str] = attr.ib(factory=set)
    _names: Set[str] = attr.ib(factory=set)

    def add_repo(self, *, url: str, name: str = None, from_config: bool = False) -> bool:
        if url in self._urls:
            return False

        # try to interpret URL as local path
        if '://' not in url:
            path = Path(url)
            if path.exists():
                if name is None:
                    name = path.name
                if name in self._names:
                    return False
                full_path = str(path.resolve())
                if full_path in self._urls:
                    return False
                self._names.add(name)
                self._urls.update({url, full_path})
                self.repos.append(WarehouseLocalRepo(
                    name=name,
                    path=path,
                    prereleases=self.prereleases,
                    from_config=from_config,
                ))
                return True
            if '.' not in url and 'localhost' not in url:
                raise FileNotFoundError('cannot find directory: {}'.format(url))

        if not urlparse(url).scheme:
            url = 'https://' + url

        if name is None:
            name = urlparse(url).hostname
        if name in self._names:
            return False
        if not name:
            name = 'pypi'
        self._names.add(name)

        cls: Union[Type[WarehouseAPIRepo], Type[WarehouseSimpleRepo]]
        if _has_api(url=url):
            cls = WarehouseAPIRepo
        else:
            cls = WarehouseSimpleRepo
        repo = cls(
            name=name,
            url=url,
            prereleases=self.prereleases,
            from_config=from_config,
        )
        urls = {url, repo.url, repo.pretty_url}
        if urls & self._urls:
            return False
        self._urls.update(urls)
        self.repos.append(repo)
        return True

    def attach_config(self, config=None) -> None:
        """
        1. Add repositories from config into registry
        2. Add auth
        """
        # repos from config
        if config is None:
            config = global_config
        for url in config['warehouse']:
            self.add_repo(url=url, from_config=True)

        # auth
        for repo in self.repos:
            if isinstance(repo, WarehouseLocalRepo):
                continue
            host = urlparse(repo.pretty_url).hostname
            # pypi doesn't have private packages
            if host in WAREHOUSE_DOMAINS:
                continue
            for cred in config['auth']:
                if cred['hostname'] == host:
                    repo.auth = Auth(**cred)

    def make(self, name: str) -> 'RepositoriesRegistry':
        """Return new RepositoriesRegistry where repo with given name goes first
        """
        repos = []
        for repo in self.repos:
            if repo.name == name:
                repos.append(repo)
                break
        else:
            raise LookupError('cannot find repo with given name: {}'.format(name))
        for repo in self.repos:
            if repo.name != name:
                repos.append(repo)
        return type(self)(repos=repos, prereleases=self.prereleases)

    def get_releases(self, dep) -> tuple:
        first_exception: Optional[Exception] = None
        for repo in self.repos:
            try:
                return repo.get_releases(dep=dep)
            except PackageNotFoundError as exc:
                if first_exception is None:
                    first_exception = exc
        if first_exception is None:
            raise LookupError('no repositories in registry')
        raise first_exception

    async def get_dependencies(self, name: str, version: str, extra: Optional[str] = None) -> tuple:
        first_exception: Optional[Exception] = None
        for repo in self.repos:
            try:
                return await repo.get_dependencies(name=name, version=version, extra=extra)
            except PackageNotFoundError as exc:
                if first_exception is None:
                    first_exception = exc
        if first_exception is None:
            raise LookupError('no repositories in registry')
        raise first_exception

    def search(self, query: Iterable[str]) -> List[Dict[str, str]]:
        for repo in self.repos:
            if isinstance(repo, WarehouseAPIRepo):
                return repo.search(query=query)
        return self.repos[0].search(query=query)

    async def download(self, name: str, version: str, path: Path) -> bool:
        for repo in self.repos:
            if not isinstance(repo, WarehouseLocalRepo):
                return await repo.download(name=name, version=version, path=path)
        return await self.repos[0].download(name=name, version=version, path=path)

    # properties

    @property
    def name(self) -> str:  # type: ignore
        return self.repos[0].name

    @property  # type: ignore
    def url(self) -> str:  # type: ignore
        return self.repos[0].url

    @url.setter
    def url(self, url: str):
        self.repos[0].url = url

    @property
    def pretty_url(self) -> str:
        return self.url

    @pretty_url.setter
    def pretty_url(self, url: str):
        self.repos[0].url = url

    @property
    def propagate(self) -> bool:  # type: ignore
        return self.repos[0].propagate
