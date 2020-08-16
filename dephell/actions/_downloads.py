# built-in
from collections import defaultdict
from datetime import date, timedelta
from itertools import zip_longest
from typing import Any, DefaultDict, Dict, Iterator, List, Sequence

# external
import attr

# app
from ..networking import requests_session


RECENT_URL = 'https://pypistats.org/api/packages/{}/recent'
CATEGORIES_URLS = dict(
    pythons='https://pypistats.org/api/packages/{}/python_minor',
    systems='https://pypistats.org/api/packages/{}/system',
)


@attr.s()
class DateList:
    start = attr.ib(type=date)
    end = attr.ib(type=date)
    _data = attr.ib(factory=dict, repr=False, type=Dict[str, int])

    def add(self, date: str, value: int):
        self._data[date] = value

    def __iter__(self) -> Iterator[int]:
        moment = self.start
        while moment <= self.end:
            yield self._data.get(str(moment), 0)
            moment += timedelta(1)


def make_chart(values: Sequence[int], group: int = None, ticks: str = '_▁▂▃▄▅▆▇█') -> str:
    peek = max(values)
    if peek == 0:
        chart = ticks[-1] * len(values)
    else:
        chart = ''
        for value in values:
            index = round((len(ticks) - 1) * value / peek)
            chart += ticks[int(index)]
    if group:
        chunks = map(''.join, zip_longest(*[iter(chart)] * group, fillvalue=' '))
        chart = ' '.join(chunks).strip()
    return chart


def get_total_downloads(name: str) -> Dict[str, int]:
    url = RECENT_URL.format(name)
    with requests_session() as session:
        response = session.get(url)
    response.raise_for_status()
    body = response.json()['data']
    return dict(
        day=body['last_day'],
        week=body['last_week'],
        month=body['last_month'],
    )


def get_downloads_by_category(*, category: str, name: str) -> List[Dict[str, Any]]:
    url = CATEGORIES_URLS[category].format(name)
    with requests_session() as session:
        response = session.get(url)
    response.raise_for_status()
    body = response.json()['data']

    yesterday = date.today() - timedelta(1)
    grouped: DefaultDict[str, DateList]
    grouped = defaultdict(lambda: DateList(start=yesterday - timedelta(30), end=yesterday))
    for line in body:
        category = line['category'].replace('.', '')
        grouped[category].add(date=line['date'], value=line['downloads'])

    result = []
    for category, dates in grouped.items():
        downloads = list(dates)
        if sum(downloads) == 0:
            continue
        result.append(dict(
            category=category,
            day=downloads[-1],
            week=sum(downloads[-7:]),
            month=sum(downloads),
            chart=make_chart(downloads[-28:], group=7),
        ))
    return result
