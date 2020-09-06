# built-in
from typing import Any, Dict, TextIO

# app
from .imports import lazy_import


ruamel_yaml = lazy_import('ruamel.yaml', package='ruamel.yaml')
py_yaml = lazy_import('yaml', package='PyYAML')


def yaml_load(stream: TextIO, *, safe: bool = True):
    if safe:
        parser = ruamel_yaml.YAML(typ='safe')
    else:
        parser = ruamel_yaml.YAML()

    # first of all, try to parse by ruamel.yaml
    try:
        return parser.load(stream)
    except Exception:
        pass

    # on error try to parse by PyYAML
    if safe:
        return py_yaml.safe_load(stream)
    return py_yaml.load(stream)


def yaml_dump(data: Dict[str, Any], stream: TextIO):
    parser = ruamel_yaml.YAML()
    parser.dump(data, stream)
