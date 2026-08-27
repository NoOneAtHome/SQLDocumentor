SELECT us.object_id, us.index_id, us.user_seeks, us.user_scans, us.user_lookups, us.user_updates,
       us.last_user_seek, us.last_user_scan, us.last_user_lookup, us.last_user_update
FROM sys.dm_db_index_usage_stats us
WHERE us.database_id = DB_ID();
