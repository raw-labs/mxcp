{{ config(materialized='table') }}

SELECT 
    u.user_id,
    u.username,
    u.email,
    COUNT(o.id) as total_orders,
    COALESCE(SUM(o.amount), 0) as total_spent,
    MAX(o.created_at) as last_order_date
FROM {{ ref('users') }} u
LEFT JOIN {{ ref('raw_orders') }} o ON u.user_id = o.user_id
GROUP BY u.user_id, u.username, u.email
