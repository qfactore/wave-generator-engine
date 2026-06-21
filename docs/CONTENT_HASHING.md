# Content Hashing

Source Profiles, Delivery Presets, LeverSets, lever registries, views, and fork
records use SHA-256 over canonical UTF-8 JSON.

Keys are sorted, separators are stable, insignificant whitespace is absent, and
non-finite numbers are rejected. The document's own top-level `content_hash`
field is excluded; no other metadata is excluded. Semantic changes therefore
change the hash while key order and formatting do not.
