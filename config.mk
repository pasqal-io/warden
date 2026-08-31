# Install additional depencies for the database

# Whether to install the PostgreSQL/MariaDB packages database respectively
# If you do decide to change the actual backend, you will have to run the install command again
# Prefer overriding these in the environment (WITH_PG=1 make install) over editing
# this file: it is tracked by git, and a local edit makes an upgrade's checkout fail.
WITH_PG?=0
WITH_MARIADB?=0

# The Python interpreter to use, 3.11 and 3.12 are supported
PYTHON?=python3
