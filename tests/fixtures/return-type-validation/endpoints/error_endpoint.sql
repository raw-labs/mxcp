SELECT name, age, extra
FROM (
    SELECT * FROM (
        VALUES 
            ('Alice', 30, NULL),
            ('Bob', 25, NULL)
    ) AS t1(name, age, extra)
    WHERE $error_type = 'multiple_rows'
    UNION ALL
    SELECT * FROM (
        VALUES 
            ('Alice', 30, NULL)
    ) AS t2(name, age, extra)
    WHERE $error_type = 'no_rows' AND 1=0
    UNION ALL
    SELECT * FROM (
        VALUES 
            ('Alice', 30, 'extra')
    ) AS t3(name, age, extra)
    WHERE $error_type = 'multiple_columns'
    UNION ALL
    SELECT * FROM (
        VALUES 
            ('Alice', 30, NULL)
    ) AS t4(name, age, extra)
    WHERE $error_type NOT IN ('multiple_rows', 'no_rows', 'multiple_columns')
) AS result 