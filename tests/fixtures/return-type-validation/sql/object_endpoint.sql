SELECT name, age 
FROM (VALUES 
    ('Alice', 30),
    ($name, $age)
) AS t(name, age)
LIMIT 1 