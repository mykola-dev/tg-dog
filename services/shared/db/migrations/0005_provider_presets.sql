-- Migrate provider_queue from list-of-strings to list of preset objects
-- and add opencode_command to scoring JSON
UPDATE pipeline_config
SET scoring = jsonb_set(
    jsonb_set(
        scoring,
        '{provider_queue}',
        '[{"name": "opencode", "provider_id": "opencode_cli"}]'::jsonb
    ),
    '{opencode_command}',
    '""'::jsonb
)
WHERE id = 1;
