from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from logging import Logger

from requests_cache import CachedSession

from trainline_location import get_station_id


CURRENCY_CODE = 'GBP'
DEFAULT_COUNTRY = 'GB'
TRAINLINE_DOMAIN = 'www.thetrainline.com'
TRAINLINE_URL = 'https://' + TRAINLINE_DOMAIN
LOCATIONS_SEARCH_URI = '/api/locations-search/v1/search?'
JOURNEY_SEARCH_URI = '/api/journey-search/'

request_headers = {
    'Accept': 'application/json',
    'Content-Type': 'text/plain;charset=UTF-8',
    'Accept-Encoding': 'gzip, deflate, br',
}


@dataclass()
class FeedConfig():
    session: CachedSession
    logger: Logger
    useragent: str = ''
    newrelic_version: str = ''
    country: str = DEFAULT_COUNTRY
    url: str = TRAINLINE_URL
    domain: str = TRAINLINE_DOMAIN
    locations_uri: str = LOCATIONS_SEARCH_URI
    journey_uri: str = JOURNEY_SEARCH_URI
    currency: str = CURRENCY_CODE
    headers: dict = field(default_factory=dict)


@dataclass
class QueryStatus():
    ok: bool = True
    errors: list[str] = field(default_factory=list)

    def refresh(self):
        self.ok = False if self.errors else True


@dataclass(kw_only=True)
class _BaseQuery:
    status: QueryStatus
    config: FeedConfig
    from_code: str = 'BHM'
    to_code: str = 'EUS'
    from_id: str = ''
    to_id: str = ''
    journey: str = ''
    time_str: str = datetime.now().strftime("%H%M")
    date_str: str = datetime.now().strftime("%Y%m%d")
    timestamp: datetime = datetime.now()
    weeks_ahead_str: str = '0'
    weeks_ahead: int = 0

    def init_station_ids(self, feed_config):
        self.from_id = get_station_id(self.from_code, feed_config)
        self.to_id = get_station_id(self.to_code, feed_config)

        if not (self.from_id and self.to_id):
            self.status.errors.append('Missing station id(s)')

    def init_journey(self):
        self.journey = self.from_code.upper() + '>' + self.to_code.upper()

    def init_timestamp(self):
        self.timestamp = datetime.strptime(
            self.date_str + ' ' + self.time_str, "%Y%m%d %H%M")

    def init_weeks_ahead(self):
        if self.weeks_ahead_str:
            self.weeks_ahead = int(self.weeks_ahead_str)

    def validate_departure_time(self):
        if self.time_str:
            time_rules = [self.time_str.isnumeric(), len(self.time_str) == 4]

            if not all(time_rules):
                self.status.errors.append('Invalid departure time')

    def validate_departure_date(self):
        if self.date_str:
            temp_date = datetime.strptime(self.date_str, "%Y%m%d").date()

            date_rules = [self.date_str.isnumeric(), len(self.date_str) == 8]

            if not all(date_rules):
                self.status.errors.append('Invalid departure date')

            if temp_date < datetime.now().date():
                self.status.errors.append('Departure date has passed')

    def validate_station_code(self):
        try:
            station_code_rules = [self.from_code.isalpha(), len(self.from_code) == 3,
                                  self.to_code.isalpha(), len(self.to_code) == 3]

            if not all(station_code_rules):
                raise TypeError()

        except (TypeError, AttributeError):
            self.status.errors.append('Invalid station code(s)')

    def validate_weeks_ahead(self):
        if self.weeks_ahead:
            if not self.weeks_ahead_str.isnumeric():
                self.status.errors.append('Invalid week count')


@dataclass()
class TrainlineQuery(_BaseQuery):

    def __post_init__(self):
        self.validate_station_code()
        self.validate_departure_time()
        self.validate_departure_date()
        self.validate_weeks_ahead()
        self.status.refresh()

        if self.status.ok:
            self.init_station_ids(self.config)
            self.init_journey()
            self.init_timestamp()
            self.init_weeks_ahead()
            self.status.refresh()
