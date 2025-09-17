{{ config(materialized='table') }}

SELECT 
    id as user_id,
    name as username,
    email,
    created_at::DATE as created_date,
    status
FROM {{ ref('raw_users') }}
WHERE status = 'active'
