import json
import time
from datetime import datetime, timedelta
from flask import abort
from requests.exceptions import JSONDecodeError, RequestException

from json_feed_data import JSONFEED_VERSION_URL, JsonFeedItem, JsonFeedTopLevel


CONNECT_WAIT_SEC = 2


def reset_query_session(query):
    query.config.useragent = None
    query.config.session.cookies.clear()
    query.config.session.cache.clear()


def get_response_dict(url, query, body):
    config = query.config
    logger = config.logger
    session = config.session
    log_header = (
        f"{query.journey} {body['transitDefinitions'][0]['journeyDate']['time']}"
    )

    config.headers["User-Agent"] = config.useragent
    config.headers["x-version"] = config.newrelic_version
    session.headers = config.headers

    logger.debug(f"{log_header} - querying endpoint: {url}")

    try:
        response = session.post(url, data=json.dumps(body))
    except RequestException as rex:
        logger.error(f"{log_header} - {type(rex)}: {rex}")
        return None

    # return HTTP error code
    if not response.ok:
        if response.status_code == 400 and "InvalidFormat" in response.text:
            # ignore errors due to past departure dates
            return None

        if response.text.find("captcha") != -1:
            bot_msg = f"{log_header} - bot detected, resetting session"

            logger.error(bot_msg)
            reset_query_session(query)

            abort(503, bot_msg)

        logger.error(f"{log_header} - HTTP {response.status_code}")
        abort(response.status_code, response.text)
    else:
        logger.debug(f"{log_header} - response cached: {response.from_cache}")

    try:
        return response.json()
    except JSONDecodeError as jdex:
        logger.error(f"{log_header} - HTTP {response.status_code} {type(jdex)}: {jdex}")
        return None


def get_top_level_feed(query, feed_items):

    title_strings = [query.config.domain, query.journey]

    base_url = query.config.url

    json_feed = JsonFeedTopLevel(
        version=JSONFEED_VERSION_URL,
        items=feed_items,
        title=" - ".join(title_strings),
        home_page_url=base_url,
        favicon=query.config.favicon_url,
    )

    return json_feed


def generate_items(query, result_dict):
    item_title_text = query.config.domain + " - " + query.journey

    def get_price_entry(date, price):
        return f"{date.replace(tzinfo=None).isoformat(timespec='minutes')}: {price}"

    iso_timestamp = datetime.now().isoformat("T")

    item_link_url = query.config.url

    content_body_list = [
        f"{get_price_entry(date, price)}" for date, price in result_dict.items()
    ]

    content_body = "<br/>".join(content_body_list)

    feed_item = JsonFeedItem(
        id=iso_timestamp,
        url=item_link_url,
        title=item_title_text,
        content_html=content_body + "<br/>" if content_body else "",
        date_published=iso_timestamp,
    )

    return feed_item


def get_request_bodies(query, dates):
    request_dict = {}
    for date in dates:
        request_body = {
            "passengers": [],
            "transitDefinitions": [
                {
                    "direction": "outward",
                    "origin": query.from_id,
                    "destination": query.to_id,
                    "journeyDate": {"type": "departAfter", "time": date.isoformat()},
                }
            ],
            "type": "single",
            "maximumJourneys": 1,
        }
        request_dict[date] = request_body

    return request_dict


def get_item_listing(query):
    query_url = query.config.url + query.config.journey_uri

    dates = [
        query.query_dt + timedelta(days=(7 * x)) for x in range(query.weeks_ahead + 1)
    ]

    request_dict = get_request_bodies(query, dates)

    result_dict = {}

    for date, body in request_dict.items():

        json_dict = get_response_dict(query_url, query, body)

        if json_dict:
            # assume next journey is closest to requested time
            journeys = json_dict["data"]["journeySearch"]["journeys"]

            if journeys and journeys.values():
                first_journey = list(journeys.values())[0]

                departure_dt = datetime.fromisoformat(first_journey["departAt"])

            fares = json_dict["data"]["journeySearch"]["fares"]

            if isinstance(fares, dict):
                fare_list = list(fares.values())
                fare_types = json_dict.get("data").get("fareTypes")

                selected_fare = None

                if len(fare_list) == 1:
                    selected_fare = fare_list[0]
                elif len(fare_list) > 1:
                    fare_prices = [
                        float(fare["fullPrice"]["amount"]) for fare in fare_list
                    ]
                    lowest_price = min(fare_prices)
                    selected_fare = [
                        fare
                        for fare in fare_list
                        if fare["fullPrice"]["amount"] == lowest_price
                    ][0]

                if selected_fare:
                    remaining_seats = selected_fare["availability"].get("remaining")

                    fare_type_name = [
                        fare_type["name"]
                        for fare_type in fare_types.values()
                        if fare_type["id"] == selected_fare["fareType"]
                    ][0]

                    fare_price = selected_fare["fullPrice"]
                    currency = fare_price["currencyCode"].replace("GBP", "£")

                    fare_text = [
                        currency,
                        f"{fare_price['amount']:.2f}",
                        f"({fare_type_name})",
                    ]

                    if query.seats_left and remaining_seats:
                        fare_text.insert(2, f"({remaining_seats} left)")

                    result_dict[departure_dt] = " ".join(fare_text)
        else:
            result_dict[date] = "Not found"
        time.sleep(CONNECT_WAIT_SEC)

    feed_items = generate_items(query, result_dict)

    json_feed = get_top_level_feed(query, [feed_items])

    return json_feed
