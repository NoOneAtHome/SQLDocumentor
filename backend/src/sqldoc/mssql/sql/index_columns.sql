SELECT ic.object_id, ic.index_id, ic.index_column_id, ic.column_id, c.name AS column_name,
       ic.key_ordinal, ic.is_descending_key, ic.is_included_column, ic.partition_ordinal
FROM sys.index_columns ic
JOIN sys.objects o ON o.object_id = ic.object_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE o.is_ms_shipped = 0 AND ic.index_id > 0;
