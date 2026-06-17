"""Compatibility shim for the old authorized_users dependency module.

Prefer importing AuthConfigDep or ensure_user_is_authorized from
warden.api.routes.dependencies.auth in new route code.
"""

from warden.api.routes.dependencies.user_authorization import (  # noqa: F401
    AuthorizedUsersDep,
    get_authorized_users,
    init_authorization,
    init_authorized_users,
)
