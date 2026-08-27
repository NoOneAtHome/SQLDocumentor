SELECT d.referencing_id, d.referencing_minor_id, d.referencing_class_desc, d.is_schema_bound_reference,
       d.referenced_class_desc, d.referenced_server_name, d.referenced_database_name,
       d.referenced_schema_name, d.referenced_entity_name, d.referenced_id, d.referenced_minor_id,
       d.is_caller_dependent, d.is_ambiguous
FROM sys.sql_expression_dependencies d
WHERE d.referencing_class = 1;
