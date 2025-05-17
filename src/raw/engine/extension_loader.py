def load_raw_extension(con):
    try:
        con.sql("INSTALL raw; LOAD raw;")
        print("RAW DuckDB extension loaded.")
    except Exception as e:
        print("Warning: failed to load RAW extension:", e)