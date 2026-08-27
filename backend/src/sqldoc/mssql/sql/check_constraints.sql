SELECT cc.object_id, cc.name, cc.parent_object_id, cc.parent_column_id, cc.definition,
       cc.is_disabled, cc.is_not_trusted
FROM sys.check_constraints cc
WHERE cc.is_ms_shipped = 0;
