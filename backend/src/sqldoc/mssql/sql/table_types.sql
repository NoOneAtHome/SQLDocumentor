SELECT tt.type_table_object_id AS object_id, SCHEMA_NAME(tt.schema_id) AS schema_name, tt.name,
       'TT' AS type, 'TABLE_TYPE' AS type_desc, o.create_date, o.modify_date, NULL AS parent_object_id
FROM sys.table_types tt
JOIN sys.objects o ON o.object_id = tt.type_table_object_id;
