# db_config.py

# === MySQL Database Connection Configuration === #

DB_HOST = "localhost"                        # MySQL server hostname (default: localhost)
DB_PORT = 3306                               # MySQL server port (default: 3306)
DB_USER = "root"                             # MySQL username with database privileges
DB_PASSWORD = "Password123!"                   # Password for the database user
DB_NAME = "erebus_threat_intel_prod"        # Primary database used by ObsidianDroid platform

# === Optional Advanced Settings === #

DB_CHARSET = "utf8mb4"                       # UTF-8 multibyte charset (emoji + CJK support)
DB_ENABLE_POOLING = False                    # Reserved: Enable for multithreaded or async apps
DB_POOL_SIZE = 8                             # Connection pool size when pooling is enabled
DB_POOL_NAME = "obsidiandroid_pool"               # Stable pool name for connector reuse
