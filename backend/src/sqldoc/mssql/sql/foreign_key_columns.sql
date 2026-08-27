SELECT fkc.constraint_object_id, fkc.constraint_column_id,
       fkc.parent_object_id, fkc.parent_column_id, pc.name AS parent_column,
       fkc.referenced_object_id, fkc.referenced_column_id, rc.name AS referenced_column
FROM sys.foreign_key_columns fkc
JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id;
