SELECT i.object_id, i.index_id, i.name, i.type, i.type_desc, i.is_unique, i.is_primary_key,
       i.is_unique_constraint, i.has_filter, i.filter_definition, i.fill_factor, i.is_disabled,
       i.is_padded, ds.name AS data_space_name, ds.type AS data_space_type
FROM sys.indexes i
JOIN sys.objects o ON o.object_id = i.object_id
LEFT JOIN sys.data_spaces ds ON ds.data_space_id = i.data_space_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('U','V') AND i.index_id > 0;
