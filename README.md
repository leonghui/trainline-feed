# trainline-feed
A simple Python script to generate a [JSON Feed](https://github.com/manton/JSONFeed) for search for train tickets on [Trainline](https://www.trainline.com). Only supports single (one-way) journeys.

Served over [Flask!](https://github.com/pallets/flask/)

Use the [Docker build](https://github.com/users/leonghui/packages/container/package/trainline-feed) to host your own instance.

1. Set your timezone as an environment variable (see [docker docs]): `TZ=America/Los_Angeles`

2. Access the feed using the URL with origin and destination station codes: `http://<host>/?from=BHM&to=EUS`

3. Optionally, specify a:
    - date (yyyyMMdd): `http://<host>/?from=BHM&to=EUS&on=20221225`
    - time (hhmm): `http://<host>/?from=BHM&to=EUS&at=1200`
    - number of weeks to look ahead: `http://<host>/?from=BHM&to=EUS&weeks=2`
    - or any combination of the above

E.g.
```
Train prices from MAN (Manchester Piccadilly) to PAD (London Paddington) at 9pm:

Feed link:
http://<host>/?from=MAN&to=PAD&at=2100
```

Tested with:
- [Nextcloud News App](https://github.com/nextcloud/news)

[docker docs]:(https://docs.docker.com/compose/environment-variables/#set-environment-variables-in-containers)
