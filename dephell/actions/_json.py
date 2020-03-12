# built-in
import json
from collections import defaultdict
from functools import reduce
from typing import Optional

# app
from ..imports import lazy_import


pygments = lazy_import('pygments')
pygments_lexers = lazy_import('pygments.lexers')
pygments_formatters = lazy_import('pygments.formatters')
tabulate = lazy_import('tabulate')


def _each(value):
    if isinstance(value, list):
        new_value = defaultdict(list)
        for line in value:
            for name, field in line.items():
                new_value[name].append(field)
        return dict(new_value)

    new_value = []
    for line in zip(*value.values()):
        new_value.append(dict(zip(value.keys(), line)))
    return new_value


def _flatten(value) -> list:
    if not isinstance(value, (list, tuple)):
        return [value]
    new_value = []
    for element in value:
        new_value.extend(_flatten(element))
    return new_value


def _flatdict(data, sep: str = '.', prefix: str = ''):
    if isinstance(data, (list, tuple)):
        return [_flatdict(row) for row in data]
    if isinstance(data, dict):
        result = dict()
        for key, value in data.items():
            new_key = str(key)
            if prefix:
                new_key = prefix + sep + new_key
            if isinstance(value, dict):
                result.update(_flatdict(data=value, sep=sep, prefix=new_key))
            else:
                result[new_key] = value
        return result
    return data


FILTERS = {
    'each()': _each,
    'first()': lambda v: v[0],
    'flatten()': _flatten,
    'last()': lambda v: v[-1],
    'len()': len,
    'max()': max,
    'min()': min,
    'reverse()': lambda v: v[::-1],
    'sort()': sorted,
    'sum()': sum,
    'type()': lambda v: type(v).__name__,
    'zip()': lambda v: list(map(list, zip(*v))),

    # aliases
    '#': _each,
    'count()': len,
    'flat()': _flatten,
    'latest()': lambda v: v[-1],
    'length()': len,
    'reversed()': lambda v: v[::-1],
    'size()': len,
    'sorted()': sorted,
}


def getitem(value, key):
    # function
    filter = FILTERS.get(key)
    if filter is not None:
        return filter(value)

    # sum of fields
    if '+' in key:
        keys = key.split('+')
        return {key: value[key] for key in keys}

    # index
    if key.isdigit():
        key = int(key)
        return value[key]

    # slice
    if ':' in key:
        left, _sep, right = key.partition(':')
        if (not left or left.isdigit()) and (not right or right.isdigit()):
            left = int(left) if left else 0
            right = int(right) if right else None
            return value[left:right]

    # field
    return value[key]


def _beautify(data, *, colors: bool, table: bool) -> str:
    """
    1. Returns table if `table=True`
    1. Returns colored JSON if `json=True`
    1. Returns plain JSON otherwise.
    """
    if table:
        # one dict
        if isinstance(data, dict):
            return tabulate.tabulate(
                _flatdict(data).items(),
                headers=('key', 'value'),
                tablefmt='fancy_grid',
            )
        # list of dicts
        if isinstance(data, list) and data and isinstance(data[0], dict):
            table = []
            for row in data:
                row = _flatdict(row)
                keys = tuple(row)
                row = [v for _, v in sorted(row.items())]
                table.append(row)
            return tabulate.tabulate(
                table,
                headers=keys,
                tablefmt='fancy_grid',
            )

    json_params = dict(indent=2, sort_keys=True, ensure_ascii=False)
    dumped = json.dumps(data, **json_params)
    if not colors:
        return dumped
    return pygments.highlight(
        code=dumped,
        lexer=pygments_lexers.JsonLexer(),
        formatter=pygments_formatters.TerminalFormatter(),
    )


def make_json(data, key: str = None, sep: Optional[str] = '-',
              colors: bool = True, table: bool = False) -> str:
    # print all config
    if not key:
        return _beautify(data=data, colors=colors, table=table)

    if sep is None:
        return _beautify(data=data[key], colors=colors, table=table)

    keys = key.replace('.', sep).split(sep)
    value = reduce(getitem, keys, data)
    # print config section
    if isinstance(value, (dict, list)):
        return _beautify(data=value, colors=colors, table=table)

    # print one value
    return str(value)
