# Installation

1. In Home Assistant OS, open Settings → Apps → App store → Repositories.
2. Add `https://github.com/R3inoudR/RTL-SDR-P2000Receiver-HA` after this change has been merged to its default branch.
3. Install **P2000 RTL-SDR Reliable**. The initial build downloads public Debian packages.
4. Ensure the MQTT integration and a broker such as Mosquitto are running.
5. Configure the app, stop any other receiver using the same dongle, then start this app.

This release advertises **amd64 only**, matching the architecture tested in the local repair. Other architectures must be built and tested before being added to `arch`.

# Configuration

The defaults provide ten example profiles for the requested capcodes, places, fire classifications, GRIP levels and Lifeliners 1–3. **Home coordinates default to zero**: radius profiles reject everything until valid coordinates are configured. These are examples, not a universal list of emergency-service codes.

For every radius profile, replace `zone_latitude` and `zone_longitude` with your Home coordinates from Home Assistant's location settings. Distances are in kilometers. Changing the HA Home zone does not automatically update these stored coordinates.

To enable address geocoding, set `opencage.enabled` to `true` and enter your own API key in `opencage.token` in HA. Never commit keys, MQTT passwords or live `options.json` to Git.

MQTT credentials are obtained automatically from Supervisor when `mqtt.host` is omitted. Otherwise set host, port, user and password explicitly. Keep `mqtt.base_topic` and profile IDs stable to retain entity identity. Configure TLS when using an external broker.

Restart the app after changing options.

## Profile fields

| Field | Meaning |
|---|---|
| `id`, `name` | Required unique sensor ID and display name |
| `incident_type` | `middelbrand`, `grote_brand`, or `zeer_grote_brand`; mutually exclusive classification |
| `grip_level` | Integer 1–4; GRIP1, GRIP-1 and GRIP: 1 forms are recognized |
| `towns` | Comma-separated incident city names; matches the parsed city, not a street-name substring |
| `capcode` | Comma-separated 9-digit strings, for example `001200298,001201949` |
| `discipline`, `region`, `keyword` | Comma-separated wildcard patterns, matched without case sensitivity |
| `zone_radius` | Positive maximum distance in kilometers; omitting it disables distance filtering |
| `zone_latitude`, `zone_longitude` | Required valid Home coordinates for a radius profile |

All configured criteria for a profile must match. Values within one comma-separated field are alternatives. When a message mentions multiple GRIP levels, the highest stated level is selected.

Default ranges: middelbrand 10 km, grote brand 15 km, zeer grote brand 20 km, GRIP 1 30 km, GRIP 2 50 km, Lifeliners 1–3 20 km. GRIP 3–4 have no distance filter. Nationwide means every matching message the dongle actually receives.

Lifeliner capcodes included: `000120901`, `001420059`, `000923993`. Lifeliner 4 has no confirmed direct P2000 capcode in these profiles; MEDIC01/Waddenheli information codes are not substituted for it.

# Strict location handling

A radius profile rejects missing, non-finite, unverified and ambiguous coordinates. OpenCage must return a Dutch street result matching the parsed city and street, with a bounding box. City-only results are rejected.

Acceptance requires the distance to Home **plus** the maximum distance from the returned point to a bounding-box corner to fit within the radius. The bounding box is a conservative spatial check; it is not a statistical confidence interval or measured GPS accuracy.

The extra attributes `location_verified`, `location_uncertainty_km` and `location_type` explain accepted location data. Place/capcode profiles without a radius can receive messages without location data.

Only messages matching a radius profile's other criteria trigger geocoding. Verified results are cached for 30 days in `/data/p2000.sqlite3`. The old unverified geocode cache is not used.

If no reliable street can be parsed, or geocoding fails, a radius message is intentionally skipped. Highway-only messages, unusual street spellings and incomplete addresses can therefore be missed. Reception also depends on antenna placement and signal quality. The software is not a guaranteed emergency alerting service.

# MQTT and duplicates

Discovery uses stable IDs and the existing `p2000_rtlsdr` topic layout. Sensors are created at startup and stale last-message states are reset to `unknown`; this is expected until a valid message arrives.

Repeated identical text is suppressed per profile for 120 seconds. One incident may legitimately match different profiles, such as a local capcode and a local fire category. Consumer automations may need to deduplicate across profiles.

Publishing uses QoS 1 and retries failed delivery while the app runs. The queue is bounded and kept in memory: a restart, long outage or reception loss can still lose messages. MQTT QoS 1 also permits transport-level duplicates.

# Migration from the local repaired app

The local `local_p2000_reliable` repair uses the same profile IDs and MQTT topics. Copy its options through the HA app configuration UI, install this repository version, stop the local receiver, and start the repository receiver. Do not run both receivers simultaneously. New app storage starts with a fresh geocoding cache.

Leave the working local app installed but stopped until the repository version has been checked. To roll back, stop the repository version and restart the local repair. Removing the old root-level standalone receiver is not required.

# Development and tests

Build from the repository root:

```sh
docker build -t p2000-reliable:test p2000_reliable
```

For the test command, mount the source folder (the production image intentionally excludes tests):

```sh
docker run --rm --network none --entrypoint python3 \
  -v "$PWD/p2000_reliable:/test:ro" \
  p2000-reliable:test /test/test_reliable.py
```

The suite covers the real `Main.post_data` method: Deventer outside the radius, missing GPS, near/boundary locations, geocode quality, classification, city matching, full address parsing, duplicate suppression and retry after MQTT failure. It uses fixtures and does not require a radio or API key.

An optional GitHub Actions workflow is provided as `ci/reliable-addon.yml.example`. To activate it, copy it to `.github/workflows/reliable-addon.yml` using an account or token with permission to create workflows. Until then, run the Docker build and tests above manually.
