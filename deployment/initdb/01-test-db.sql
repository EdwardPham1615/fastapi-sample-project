-- Database for tests/integration. That suite drops and recreates its tables, so it
-- must never point at the database the app runs against.
CREATE DATABASE user_profile_test OWNER user_profile;
