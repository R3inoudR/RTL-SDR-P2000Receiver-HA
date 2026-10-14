# 1.1.0

- Add an installable Home Assistant app alongside the legacy standalone receiver.
- Reject radius matches without verified Dutch street coordinates, or when the geocoding bounding box extends outside the radius.
- Separate medium, large and very large fire categories; classify GRIP levels without matching GRIP 10 as GRIP 1.
- Parse complete street names, multi-word cities and optional postal-code letters without inserting `None`.
- Preserve metadata from all capcodes and suppress repeated text per profile for 120 seconds.
- Retry failed MQTT delivery with QoS 1; discover all configured sensors on startup.
- Limit geocoding to relevant radius profiles and cache verified results separately.
- Build from public Debian packages, without a private local runtime snapshot.
