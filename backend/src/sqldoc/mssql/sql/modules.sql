SELECT m.object_id, m.definition, m.uses_ansi_nulls, m.uses_quoted_identifier, m.is_schema_bound,
       m.is_recompiled, m.null_on_null_input, m.execute_as_principal_id
FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id
WHERE o.is_ms_shipped = 0;
