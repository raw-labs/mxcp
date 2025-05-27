{{ config(materialized='table') }}

select *

from read_csv_auto('https://github.com/owid/covid-19-data/raw/master/public/data/hospitalizations/locations.csv')