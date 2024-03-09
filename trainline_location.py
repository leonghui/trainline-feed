from urllib.parse import urlencode


def get_station_id(station_code, config):

    base_url = config.url + config.locations_uri

    query_dict = {
        "searchTerm": station_code,
        "limit": 1,
        "locale": config.locale,
    }

    search_url = base_url + urlencode(query_dict)

    config.logger.debug(f"Querying endpoint: {search_url}")

    location_response = config.session.get(search_url)

    if location_response.ok:
        location_dict = location_response.json()
        config.logger.debug(f"Response cached: {location_response.from_cache}")

        locations = location_dict["searchLocations"]

        if locations:
            return locations[0]["code"]
        else:
            config.logger.error(f"Invalid station code: {station_code}")
    else:
        config.logger.error(f"Unable to get location: {station_code}")
