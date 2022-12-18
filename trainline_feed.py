import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import abort
from requests.exceptions import JSONDecodeError, RequestException
from requests_cache import CachedSession

from json_feed_data import JSONFEED_VERSION_URL, JsonFeedItem, JsonFeedTopLevel
from trainline_feed_data import FareTypes, TrainlineQuery


CACHE_EXPIRATION_SEC = 120
SESSION_TIMEOUT_SEC = 2

local_session = CachedSession(
    allowable_methods=('GET', 'POST'),
    stale_if_error=True,
    expire_after=CACHE_EXPIRATION_SEC,
    backend='memory',
)

req_headers = {
    'Accept': 'application/json',
    'Connection': 'keep-alive',
    'Content-Type': 'text/plain;charset=UTF-8',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://www.trainline.com',
    'DNT': '1',
    'TE': 'trailers',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}


def get_newrelic_version(query):
    version_pattern = r'(?:window\.__VERSION__=")([0-9.]{9})"'

    init_response = local_session.get(query.config.url)
    query.config.logger.debug(
        f"{query.journey} - querying endpoint: {query.config.url}")
    match = re.search(version_pattern, init_response.text)
    if match:
        query.config.newrelic_version = match[1]
        req_headers['x-version'] = query.config.newrelic_version


def get_response_dict(url, query, body):
    logger = query.config.logger

    req_headers['User-Agent'] = query.config.useragent
    local_session.headers = req_headers

    if not query.config.session.cookies or not query.config.newrelic_version:
        get_newrelic_version(query)

    logger.debug(
        f"{query.journey} - querying endpoint: {url}")

    try:
        response = local_session.post(url, data=json.dumps(body),
                                      timeout=SESSION_TIMEOUT_SEC)
    except RequestException as rex:
        query.config.session.cookies.clear()    # clear cookies
        logger.error(f"{query.journey} - exception: {rex}")
        return None

    # return HTTP error code
    if not response.ok:
        if response.text.find('captcha'):
            bot_msg = f"{query.journey} - bot detected"
            logger.error(bot_msg)
            query.config.useragent = None   # clear user-agent
            query.config.session.cookies.clear()    # clear cookies

            abort(503, bot_msg)
        else:
            logger.error(f"{query.journey} - error from source")
            logger.debug(
                f"{query.journey} - dumping input: {response.text}")
        return None
    else:
        logger.debug(
            f"{query.journey} - response cached: {response.from_cache}")

    try:
        return response.json()
    except JSONDecodeError as jdex:
        logger.error(f"{query.journey} - exception: {jdex}")
        return None


def get_top_level_feed(base_url, query, feed_items):

    parse_object = urlparse(base_url)
    domain = parse_object.netloc
    origin_code = query.from_code.upper()
    dest_code = query.to_code.upper()

    title_strings = [domain, origin_code + '>' + dest_code]

    if isinstance(query, TrainlineQuery):
        home_page_url = base_url

    json_feed = JsonFeedTopLevel(
        version=JSONFEED_VERSION_URL,
        items=feed_items,
        title=' - '.join(title_strings),
        home_page_url=home_page_url,
        favicon=base_url + '/favicon.ico'
    )

    return json_feed


def generate_items(query, result_dict):
    base_url = query.config.url

    item_title_text = base_url + ' - ' + query.journey

    def get_price_entry(date, price):
        return f"<p>{date.isoformat(timespec='minutes').replace('+00:00', 'Z')}" + \
            f": {price}</p>"

    content_body_list = [
        f"{get_price_entry(date, price)}" for date, price in result_dict.items()]

    timestamp = datetime.now().timestamp()

    def get_formatted_timestamp():
        return datetime.fromtimestamp(timestamp) \
            .strftime('%d %B %Y %I:%M%p')

    timestamp_html = f"<p>Last updated: {get_formatted_timestamp()}</p>"

    item_link_url = base_url

    content_body_list.append(timestamp_html)
    content_body = ''.join(content_body_list)

    feed_item = JsonFeedItem(
        id=datetime.utcfromtimestamp(timestamp).isoformat('T'),
        url=item_link_url,
        title=item_title_text,
        content_html=content_body,
        date_published=datetime.utcfromtimestamp(timestamp).isoformat('T')
    )

    return feed_item


def get_request_bodies(query, dates):
    request_dict = {}
    for date in dates:
        request_body = {
            'transitDefinitions': [
                {
                    'direction': 'outward',
                    'origin': query.from_id,
                    'destination': query.to_id,
                    'journeyDate': {
                        'type': 'departAfter',
                        'time': date.isoformat()
                    }
                }
            ],
            'type': 'single',
            'maximumJourneys': 1,
            'requestedCurrencyCode': query.config.currency
        }
        request_dict[date] = request_body

    return request_dict


def get_item_listing(query):
    base_url = query.config.url

    query_url = base_url + query.config.journey_uri

    dates = [query.timestamp + timedelta(days=(7 * x))
             for x in range(query.weeks_ahead + 1)]

    request_dict = get_request_bodies(query, dates)

    result_dict = {}

    for date, body in request_dict.items():

        json_dict = get_response_dict(query_url, query, body)

        if json_dict:
            # assume next journey is closest to requested time
            journeys = json_dict['data']['journeySearch']['journeys']

            if journeys and journeys.values():
                first_journey = list(journeys.values())[0]

                departure_dt = datetime.fromisoformat(
                    first_journey['departAt'])
                # arrival_dt = datetime.fromisoformat(
                #     first_journey['arriveAt'])

            fares = json_dict['data']['journeySearch']['fares']

            if isinstance(fares, dict):
                fare_list = list(fares.values())
                fare_types = json_dict['data']['fareTypes']
                advance_fare_type_ids = [fare_type['id'] for fare_type in list(
                    fare_types.values())
                    if fare_type['name'] == FareTypes.ADVANCE_SINGLE or
                    fare_type['name'] == FareTypes.OFFPEAK_DAY_SINGLE]

                advance_fares = [
                    fare for fare in fare_list if fare['fareType'] in advance_fare_type_ids]

                selected_fare = None

                if len(advance_fares) == 1:
                    selected_fare = advance_fares[0]
                elif len(advance_fares) > 1:
                    fare_prices = [float(fare['fullPrice']['amount'])
                                   for fare in advance_fares]
                    lowest_price = min(fare_prices)
                    selected_fare = [
                        fare for fare in advance_fares
                        if fare['fullPrice']['amount'] == lowest_price][0]

                if selected_fare:
                    result_dict[departure_dt] = query.config.currency + \
                        str(selected_fare['fullPrice']['amount'])
        else:
            result_dict[date] = 'Not found'

    # json_feed = get_top_level_feed(base_url, query, [])

    # if not result_dict:
    #     logger.info(query.journey + ' - fares not found')
    #     return json_feed

    feed_items = generate_items(query, result_dict)

    json_feed = get_top_level_feed(base_url, query, [feed_items])

    return json_feed
