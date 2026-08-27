SELECT t.object_id, t.name, t.parent_id, t.type_desc, t.is_disabled, t.is_instead_of_trigger,
       (SELECT STRING_AGG(te.type_desc, ',') FROM sys.trigger_events te WHERE te.object_id = t.object_id) AS events
FROM sys.triggers t
WHERE t.parent_class = 1 AND t.is_ms_shipped = 0;
