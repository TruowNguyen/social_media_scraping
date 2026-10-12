"""Legacy paths behavior extracted without changing data policies."""

import os

LOG_DIR = "logs"

KEYWORDS_DIR = "keywords"

SOURCES_DIR = "sources"

ASSETS_REGISTRY_DIR = "assets-registry"

DEDUP_DIR = "dedup"

SESSIONS_DIR = "sessions"

ASSET_REGISTRY_PATH = os.path.join(ASSETS_REGISTRY_DIR, "asset-registry.json")
