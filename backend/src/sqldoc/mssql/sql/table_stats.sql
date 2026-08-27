SELECT ps.object_id,
       SUM(CASE WHEN ps.index_id IN (0, 1) THEN ps.row_count ELSE 0 END) AS row_count,
       SUM(CASE WHEN ps.index_id IN (0, 1)
                THEN ps.in_row_data_page_count + ps.lob_used_page_count + ps.row_overflow_used_page_count
                ELSE 0 END) * 8 AS data_kb,
       (SUM(ps.used_page_count)
        - SUM(CASE WHEN ps.index_id IN (0, 1)
                   THEN ps.in_row_data_page_count + ps.lob_used_page_count + ps.row_overflow_used_page_count
                   ELSE 0 END)) * 8 AS index_kb,
       SUM(ps.reserved_page_count) * 8 AS reserved_kb,
       COUNT(DISTINCT ps.partition_number) AS partition_count,
       MAX(CASE WHEN ps.index_id = 0 THEN 1 ELSE 0 END) AS is_heap,
       MIN(p.data_compression_desc) AS compression_min,
       MAX(p.data_compression_desc) AS compression_max
FROM sys.dm_db_partition_stats ps
JOIN sys.partitions p ON p.partition_id = ps.partition_id
JOIN sys.objects o ON o.object_id = ps.object_id
WHERE o.type = 'U' AND o.is_ms_shipped = 0
GROUP BY ps.object_id;
