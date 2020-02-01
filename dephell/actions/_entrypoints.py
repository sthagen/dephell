# built-in
from logging import getLogger
from typing import Optional, Tuple

# external
from dephell_venvs import VEnv

# app
from ..constants import IS_WINDOWS
from ..converters import EggInfoConverter
from ..models import EntryPoint


logger = getLogger('dephell.actions')


def get_entrypoints(*, venv: VEnv, name: str) -> Optional[Tuple[EntryPoint, ...]]:
    if not venv.lib_path:
        logger.critical('cannot locate lib path in the venv')
        return None
    paths = list(venv.lib_path.glob('{}*.*-info'.format(name)))
    if not paths:
        paths = list(venv.lib_path.glob('{}*.*-info'.format(name.replace('-', '_'))))
        if not paths:
            logger.critical('cannot locate dist-info for installed package')
            return None

    path = paths[0] / 'entry_points.txt'
    if not path.exists():
        # entry_points.txt can be missed for egg-info.
        # In that case let's try to find a binary with the same name as package.
        if venv.bin_path:
            paths = (
                venv.bin_path / name,
                venv.bin_path / name.replace('-', '_'),
                venv.bin_path / name.replace('_', '-'),
            )

            if IS_WINDOWS:
                paths = tuple(p.with_suffix('.exe') for p in paths)

            for path in paths:
                if path.exists():
                    return (EntryPoint(path=path, name=name), )
        logger.error('cannot find any entrypoints for package')
        return None
    return EggInfoConverter().parse_entrypoints(content=path.read_text()).entrypoints
