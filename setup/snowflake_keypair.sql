-- One-time Snowflake setup for the pipeline. Run in a Snowsight worksheet ("Run All").
--
-- Creates a dedicated SERVICE user (key-pair only, no password) and a least-privilege
-- role for ingestion + dbt + the dashboard, instead of using a personal ACCOUNTADMIN login.
-- The user name is deliberately UPPERCASE and unquoted: Snowflake clients uppercase the
-- user name in the key-pair JWT, so key-pair auth fails for quoted lowercase user names.
--
-- `python run.py keygen` creates the key pair in ~/.snowflake (outside the repo) and
-- prints this script with the public key already filled in.

use role accountadmin;

-- Dedicated XS warehouse: isolates pipeline cost and suspends after 60s idle.
create warehouse if not exists NYC_TLC_WH
    warehouse_size = 'XSMALL'
    auto_suspend = 60
    auto_resume = true
    initially_suspended = true
    comment = 'NYC TLC pipeline: ingestion, dbt, dashboard';

create role if not exists NYC_TLC_TRANSFORMER
    comment = 'Loads RAW, builds dbt layers, read by the Streamlit dashboard';
grant usage, operate on warehouse NYC_TLC_WH to role NYC_TLC_TRANSFORMER;
grant create database on account to role NYC_TLC_TRANSFORMER;

create user if not exists NYC_TLC_SVC
    type = service
    default_role = NYC_TLC_TRANSFORMER
    default_warehouse = NYC_TLC_WH
    rsa_public_key = '<PASTE_PUBLIC_KEY_BODY_HERE>'
    comment = 'Service user for the NYC TLC pipeline (key-pair auth only)';
grant role NYC_TLC_TRANSFORMER to user NYC_TLC_SVC;

-- Let your own login see and query what the pipeline builds:
grant role NYC_TLC_TRANSFORMER to user identifier(current_user());

-- Values for .env:
select
    current_organization_name() || '-' || current_account_name() as snowflake_account,
    'NYC_TLC_SVC'                                                 as snowflake_user,
    'NYC_TLC_TRANSFORMER'                                         as snowflake_role;
