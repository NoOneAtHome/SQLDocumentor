SELECT ep.class, ep.major_id, ep.minor_id, ep.name, CAST(ep.value AS nvarchar(max)) AS value
FROM sys.extended_properties ep
WHERE ep.name = 'MS_Description' AND ep.class IN (1, 2, 3, 7);
