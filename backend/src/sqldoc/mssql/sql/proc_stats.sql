SELECT x.object_id, x.kind,
       SUM(x.execution_count) AS execution_count,
       SUM(x.total_elapsed_time) AS total_elapsed_us,
       MIN(x.min_elapsed_time) AS min_elapsed_us,
       MAX(x.max_elapsed_time) AS max_elapsed_us,
       SUM(x.total_worker_time) AS total_cpu_us,
       SUM(x.total_logical_reads) AS total_logical_reads,
       MAX(x.last_execution_time) AS last_execution_time,
       MIN(x.cached_time) AS cached_time
FROM (
    SELECT object_id, 'procedure' AS kind, execution_count, total_elapsed_time, min_elapsed_time,
           max_elapsed_time, total_worker_time, total_logical_reads, last_execution_time, cached_time
    FROM sys.dm_exec_procedure_stats WHERE database_id = DB_ID()
    UNION ALL
    SELECT object_id, 'function', execution_count, total_elapsed_time, min_elapsed_time,
           max_elapsed_time, total_worker_time, total_logical_reads, last_execution_time, cached_time
    FROM sys.dm_exec_function_stats WHERE database_id = DB_ID()
    UNION ALL
    SELECT object_id, 'trigger', execution_count, total_elapsed_time, min_elapsed_time,
           max_elapsed_time, total_worker_time, total_logical_reads, last_execution_time, cached_time
    FROM sys.dm_exec_trigger_stats WHERE database_id = DB_ID()
) x
GROUP BY x.object_id, x.kind;
