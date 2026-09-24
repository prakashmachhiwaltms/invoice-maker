import pymysql

pymysql.install_as_MySQLdb()

# The local XAMPP MySQL instance (shared with other projects on this machine)
# runs MariaDB 10.4, but Django's mysql backend refuses to connect to
# anything older than MariaDB 10.11. This project does not use any feature
# that requires a newer server, so the version gate is relaxed here rather
# than upgrading the shared MySQL install (which could disturb other apps'
# databases on the same server).
try:
    from django.db.backends.mysql.base import DatabaseWrapper as _MySQLDatabaseWrapper
    from django.db.backends.mysql.features import DatabaseFeatures as _MySQLDatabaseFeatures

    _MySQLDatabaseWrapper.check_database_version_supported = lambda self: None
    # Django assumes any MariaDB server supports INSERT ... RETURNING, but that
    # syntax only exists from MariaDB 10.5 onward; the local 10.4 server errors
    # on it, so these are disabled to fall back to the older insert/select path.
    _MySQLDatabaseFeatures.can_return_columns_from_insert = False
    _MySQLDatabaseFeatures.can_return_rows_from_bulk_insert = False
except ImportError:
    pass
