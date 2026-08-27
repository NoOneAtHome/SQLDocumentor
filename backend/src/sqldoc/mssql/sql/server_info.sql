SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
       CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) AS edition,
       CAST(SERVERPROPERTY('ProductLevel') AS nvarchar(128)) AS product_level,
       CAST(@@SERVERNAME AS nvarchar(128)) AS server_name,
       CAST(SERVERPROPERTY('MachineName') AS nvarchar(128)) AS machine_name;
