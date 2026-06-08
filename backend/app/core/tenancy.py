"""Canonical multi-tenant constants.

The CellHub *master* tenant is the source of truth that per-tenant config is
backfilled and cloned from (financing terms, pricing defaults, settings). It is
seeded with a fixed UUID by ``runtime_migrations.apply_runtime_migrations`` so
every environment can reference the same id for backfills and clone-on-onboard.

Keep this module dependency-free (no DB / FastAPI imports) so it can be imported
from migrations, services, and middleware without circular-import risk.
"""

# Deterministic id for the CellHub master tenant. Chosen well outside the range
# of any real gen_random_uuid() value so the seed is recognisable and stable.
CELLHUB_MASTER_TENANT_ID = '00000000-0000-0000-0000-0000000000c1'
CELLHUB_MASTER_TENANT_NAME = 'CellHub'
