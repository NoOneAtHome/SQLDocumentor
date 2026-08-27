SELECT p.object_id, p.parameter_id, p.name, TYPE_NAME(p.user_type_id) AS type_name,
       TYPE_NAME(p.system_type_id) AS system_type_name, t.is_user_defined,
       p.max_length, p.precision, p.scale, p.is_output, p.has_default_value, p.default_value,
       p.is_readonly, t.is_table_type
FROM sys.parameters p
JOIN sys.types t ON t.user_type_id = p.user_type_id
JOIN sys.objects o ON o.object_id = p.object_id
WHERE o.is_ms_shipped = 0;
