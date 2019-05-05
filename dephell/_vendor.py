from contextlib import suppress
from importlib import import_module
from logging import getLogger


logger = getLogger('dephell._vendor')

_packages = (
    # vendored in DepHell's direct dependencies
    'appdirs',
    'colorama',
    'packaging',

    # vendored not in DepHell's dependencies graph
    'cerberus',
    'jinja2',
    'requests',
    'tomlkit',
    'yaspin',
)

_vendors = (
    # DepHell's direct dependencies
    'pip._vendor.',
    'setuptools._vendor.',

    # not in DepHell's dependencies graph
    'conda._vendor.',
    'pipenv.patched.notpip._vendor.',
    'pipenv.vendor.pythonfinder._vendor.',
    'pipenv.vendor.',
    'pkg_resources._vendor.',
    'poetry._vendor.',
    'py._vendored_packages.',
    'pythonfinder._vendor.',
)

__all__ = []
for package in _packages:
    with suppress(ImportError):
        globals()[package] = import_module(package)
        __all__.append(package)
        continue

    for vendor in _vendors:
        with suppress(Exception):
            globals()[package] = import_module(vendor + package)
            logger.debug('imported package', extra=dict(
                vendor=vendor.rstrip('.'),
                package=package,
            ))
            break
    else:
        raise ImportError('cannot import ' + package)
    __all__.append(package)
