def load_extensions(con):
    #__load_raw_extension(con)
    __load_httpfs_extension(con)

def __load_raw_extension(con):
    try:
        con.sql("INSTALL raw; LOAD raw;")
        print("RAW DuckDB extension loaded.")
    except Exception as e:
        print("Warning: failed to load RAW extension:", e)

def __load_httpfs_extension(con):
    try:
        con.sql("INSTALL httpfs; LOAD httpfs;")
        print("HTTPFS DuckDB extension loaded.")
    except Exception as e:
        print("Warning: failed to load HTTPFS extension:", e)