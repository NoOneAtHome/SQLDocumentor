SELECT o.object_id, s.name AS schema_name, o.name, RTRIM(o.type) AS type, o.type_desc,
       o.create_date, o.modify_date, o.parent_object_id
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id = o.schema_id
WHERE o.is_ms_shipped = 0
  AND o.type IN ('U','V','P','PC','FN','IF','TF','FS','FT','TR','TA','SN','SO');
