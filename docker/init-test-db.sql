-- Runs once, automatically, the first time the postgres container's data
-- volume is created. Gives tests their own database so `pytest` (which
-- truncates everything between runs, see tests/conftest.py) never
-- touches whatever's been seeded into the main dev database.
CREATE DATABASE polst_cs_test;
