SELECT name, age 
FROM (VALUES 
    ('Alice', 30),
    ('Bob', 25),
    ($name, $age)
) AS t(name, age) 