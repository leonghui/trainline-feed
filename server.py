import random
import re

from flask import Flask, abort, jsonify, request
from requests_cache import CachedSession

from mozilla_devices import DeviceType, get_useragent_list
from trainline_feed import get_item_listing
from trainline_feed_data import FeedConfig, QueryStatus, TrainlineQuery, request_headers


app = Flask(__name__)
app.config.update({'JSONIFY_MIMETYPE': 'application/feed+json'})

# app.debug = True

config = FeedConfig(
    session=CachedSession(
        allowable_methods=('GET', 'POST'),
        stale_if_error=True,
        cache_control=True,
        backend='memory'),
    logger=app.logger,
    headers=request_headers
)

useragent_list = get_useragent_list(DeviceType.PHONES, config)


def get_newrelic_version():
    version_pattern = r'(?:window\.__VERSION__=")([0-9.]*)"'

    init_response = config.session.get(config.url)
    config.logger.debug(
        f"Getting newrelic version: {config.url}")
    match = re.search(version_pattern, init_response.text)
    if match:
        config.newrelic_version = match[1]


def set_useragent():
    config.useragent = random.choice(useragent_list)
    config.session.headers['User-Agent'] = config.useragent
    config.logger.debug(f"Using user-agent: {config.useragent}")


def validate_headers():
    if not config.useragent:
        set_useragent()

    if not config.newrelic_version:
        get_newrelic_version()


def generate_response(query):
    if not query.status.ok:
        abort(400, description='Errors found: ' +
              ', '.join(query.status.errors))

    config.logger.debug(query)  # log values

    output = get_item_listing(query)
    return jsonify(output)


@app.route('/', methods=['GET'])
@app.route('/journey', methods=['GET'])
def process_listing():
    request_dict = {
        'from_code': request.args.get('from') or TrainlineQuery.from_code,
        'to_code': request.args.get('to') or TrainlineQuery.to_code,
        'time_str': request.args.get('at') or TrainlineQuery.time_str,
        'date_str': request.args.get('on') or TrainlineQuery.date_str,
        'weeks_ahead_str': request.args.get('weeks') or TrainlineQuery.weeks_ahead_str,
        'seats_left_str': request.args.get('seats_left') or TrainlineQuery.seats_left_str
    }

    validate_headers()

    query = TrainlineQuery(status=QueryStatus(), config=config, **request_dict)

    return generate_response(query)


app.run(host='0.0.0.0')
