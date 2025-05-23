import logging

def load_extensions(con):
    #__load_raw_extension(con)
    __load_httpfs_extension(con)

def __load_raw_extension(con):
    try:
        con.sql("INSTALL raw; LOAD raw;")
        logging.info("RAW DuckDB extension loaded.")
    except Exception as e:
        logging.warning("Failed to load RAW extension: %s", e)

def __load_httpfs_extension(con):
    try:
        con.sql("INSTALL httpfs; LOAD httpfs;")
        logging.info("HTTPFS DuckDB extension loaded.")
    except Exception as e:
        logging.warning("Failed to load HTTPFS extension: %s", e)