SELECT c.object_id, c.column_id, c.name,
       TYPE_NAME(c.user_type_id) AS type_name, TYPE_NAME(c.system_type_id) AS system_type_name,
       SCHEMA_NAME(t.schema_id) AS type_schema, t.is_user_defined,
       c.max_length, c.precision, c.scale, c.is_nullable, c.is_identity, c.is_computed,
       cc.definition AS computed_definition, cc.is_persisted,
       dc.name AS default_name, dc.definition AS default_definition,
       c.collation_name, ic.seed_value, ic.increment_value, c.is_rowguidcol, c.generated_always_type
FROM sys.columns c
JOIN sys.objects o ON o.object_id = c.object_id
JOIN sys.types t ON t.user_type_id = c.user_type_id
LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
LEFT JOIN sys.identity_columns ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('U','V','TF','IF','TT');
