SELECT mid.object_id, mid.index_handle, mid.equality_columns, mid.inequality_columns, mid.included_columns,
       migs.unique_compiles, migs.user_seeks, migs.user_scans, migs.last_user_seek,
       migs.avg_total_user_cost, migs.avg_user_impact
FROM sys.dm_db_missing_index_details mid
JOIN sys.dm_db_missing_index_groups mig ON mig.index_handle = mid.index_handle
JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle
WHERE mid.database_id = DB_ID();
