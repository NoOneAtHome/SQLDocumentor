SELECT d.database_id, d.name, d.collation_name, d.compatibility_level, d.state_desc, d.is_read_only
FROM sys.databases d
WHERE d.name = DB_NAME();
