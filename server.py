import random
import re

from flask import Flask, abort, jsonify, request
from requests_cache import CachedSession

from mozilla_devices import DeviceType, get_useragent_list
from trainline_feed import get_item_listing
from trainline_feed_data import (
    FeedConfig,
    QueryStatus,
    CronQuery,
    DatetimeQuery,
    request_headers,
)


app = Flask(__name__)
app.config.update({"JSONIFY_MIMETYPE": "application/feed+json"})

# app.debug = True

config = FeedConfig(
    debug=app.debug,
    session=CachedSession(
        allowable_methods=("GET", "POST"),
        stale_if_error=True,
        cache_control=False,
        expire_after=300,
        backend="memory",
    ),
    logger=app.logger,
    headers=request_headers,
)

useragent_list = get_useragent_list(DeviceType.PHONES, config)


def get_newrelic_version():
    version_pattern = r'(?:window\.__VERSION__=")([0-9.]*)"'

    init_response = config.session.get(config.url)
    config.logger.debug(f"Getting newrelic version: {config.url}")
    match = re.search(version_pattern, init_response.text)
    if match:
        config.newrelic_version = match[1]


def set_useragent():
    config.useragent = random.choice(useragent_list)
    config.session.headers["User-Agent"] = config.useragent
    config.logger.debug(f"Using user-agent: {config.useragent}")


def validate_headers():
    if not config.useragent:
        set_useragent()

    if not config.newrelic_version:
        get_newrelic_version()


def generate_response(query):
    if not query.status.ok:
        abort(400, description="Errors found: " + ", ".join(query.status.errors))

    config.logger.debug(query)  # log values

    output = get_item_listing(query)
    return jsonify(output)


@app.route("/", methods=["GET"])
@app.route("/journey", methods=["GET"])
def process_listing():
    request_dict = {
        "from_code": request.args.get("from") or DatetimeQuery.from_code,
        "to_code": request.args.get("to") or DatetimeQuery.to_code,
        "time_str": request.args.get("at") or DatetimeQuery.time_str,
        "date_str": request.args.get("on") or DatetimeQuery.date_str,
        "weeks_ahead_str": request.args.get("weeks") or DatetimeQuery.weeks_ahead_str,
        "seats_left_str": request.args.get("seats_left")
        or DatetimeQuery.seats_left_str,
    }

    validate_headers()

    query = DatetimeQuery(status=QueryStatus(), config=config, **request_dict)

    return generate_response(query)


@app.route("/cron", methods=["GET"])
def process_cron():
    request_dict = {
        "from_code": request.args.get("from") or CronQuery.from_code,
        "to_code": request.args.get("to") or CronQuery.to_code,
        "job_str": request.args.get("job") or CronQuery.job_str,
        "count_str": request.args.get("count") or CronQuery.count_str,
        "skip_weeks_str": request.args.get("skip_weeks") or CronQuery.skip_weeks_str,
        "seats_left_str": request.args.get("seats_left")
        or DatetimeQuery.seats_left_str,
    }

    validate_headers()

    query = CronQuery(status=QueryStatus(), config=config, **request_dict)

    return generate_response(query)


app.run(host="0.0.0.0", use_reloader=False)
