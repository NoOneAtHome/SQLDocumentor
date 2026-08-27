SELECT fk.object_id, fk.name, fk.parent_object_id, fk.referenced_object_id, fk.key_index_id,
       fk.delete_referential_action_desc, fk.update_referential_action_desc,
       fk.is_disabled, fk.is_not_trusted, fk.is_not_for_replication
FROM sys.foreign_keys fk
WHERE fk.is_ms_shipped = 0;
