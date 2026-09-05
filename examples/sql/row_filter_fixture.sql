-- A reproducible Unity Catalog row-level security fixture.
--
-- Run this, then ask the same question as two different people. If they get different row
-- counts, RLS resolves per caller in your workspace. If they get the same count, something is
-- wrong and it is better to find out here than in production.
--
-- The important part is not the setup. It is section 4: the negative test. A filter that is
-- attached is not necessarily a filter that runs -- DESCRIBE tells you it exists, and changing it
-- and watching the number move tells you it works.
--
-- Replace the placeholders before running:
--   ${CATALOG}   a catalog you can create schemas in
--   ${GROUP_A}   an account group you ARE a member of
--   ${GROUP_B}   an account group you are NOT a member of

-- ============================================================================================
-- 1. The fixture
-- ============================================================================================

CREATE SCHEMA IF NOT EXISTS ${CATALOG}.rls_demo;

CREATE OR REPLACE TABLE ${CATALOG}.rls_demo.project_hours (
    entry_id       STRING,
    project_group  STRING,
    project        STRING,
    hours          DECIMAL(10, 2),
    budget         DECIMAL(10, 2)
);

INSERT INTO ${CATALOG}.rls_demo.project_hours VALUES
    ('H-001', 'water-delta',  'Flood defence review',   97.25, 40100.00),
    ('H-002', 'water-delta',  'Pumping station design', 110.00, 44500.00),
    ('H-003', 'water-delta',  'Dyke reinforcement',    145.50, 61800.00),
    ('H-004', 'infra-north',  'Bridge renovation',     120.00, 48000.00),
    ('H-005', 'infra-north',  'Tunnel survey',          85.50, 31200.00),
    ('H-006', 'energy-wind',  'Offshore cable route',  340.75, 136000.00),
    ('H-007', 'energy-wind',  'Turbine foundation',    187.00, 75000.00);

-- A second table with NO filter on it. This is the positive control, and it is the reason the
-- zero in section 3 is interpretable: a caller who reads rows here but none from `project_hours`
-- has been stopped by the row filter, not by a broken connection or a missing grant.
CREATE OR REPLACE TABLE ${CATALOG}.rls_demo.unfiltered_control (
    id    STRING,
    value STRING
);

INSERT INTO ${CATALOG}.rls_demo.unfiltered_control VALUES
    ('1', 'alpha'), ('2', 'beta'), ('3', 'gamma');

-- ============================================================================================
-- 2. The filter and the mask
-- ============================================================================================

-- Row filter: members of GROUP_A see everything; members of GROUP_B see only the water-delta
-- project group. Everyone else sees nothing. Note that the default is NOTHING -- a filter whose
-- fallthrough is TRUE grants the table to the world the moment your group logic has a gap in it.
CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.hours_group_filter(project_group STRING)
RETURN
    is_account_group_member('${GROUP_A}')
    OR (is_account_group_member('${GROUP_B}') AND project_group = 'water-delta');

ALTER TABLE ${CATALOG}.rls_demo.project_hours
    SET ROW FILTER ${CATALOG}.rls_demo.hours_group_filter ON (project_group);

-- Column mask: only GROUP_A sees real budgets. Everyone else gets NULL.
-- Tested separately from the row filter below, because a mask verified only through a filter
-- that already hides the row proves nothing about the mask.
CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.budget_mask(budget DECIMAL(10, 2))
RETURN CASE WHEN is_account_group_member('${GROUP_A}') THEN budget ELSE NULL END;

ALTER TABLE ${CATALOG}.rls_demo.project_hours
    ALTER COLUMN budget SET MASK ${CATALOG}.rls_demo.budget_mask;

-- ============================================================================================
-- 3. Observe
-- ============================================================================================

-- Run these as yourself, then as a second principal with different group memberships.
-- The second principal is the whole experiment; running only as yourself proves nothing.

SELECT entry_id, project_group, project, hours, budget
FROM ${CATALOG}.rls_demo.project_hours
ORDER BY entry_id;
-- GROUP_A member : 7 rows, budget populated
-- GROUP_B member : 3 rows (water-delta only), budget NULL
-- neither        : 0 rows

-- The positive control. A caller who gets 3 here and 0 above was stopped by the FILTER.
SELECT * FROM ${CATALOG}.rls_demo.unfiltered_control;
-- every caller with SELECT: 3 rows

-- Confirm both are attached, independently of what the queries returned.
DESCRIBE TABLE EXTENDED ${CATALOG}.rls_demo.project_hours;
-- look for: Row Filter ... hours_group_filter ON (project_group)
--           Column Masks: budget -> ... budget_mask

-- ============================================================================================
-- 4. The negative test -- THIS IS THE POINT OF THE FIXTURE
-- ============================================================================================

-- Everything above is consistent with the filter being accepted and ignored. To know it runs,
-- point it at a group no row carries: a working filter then returns nothing to everybody.

CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.hours_group_filter(project_group STRING)
RETURN project_group = 'NON_EXISTING_GROUP';

SELECT count(*) FROM ${CATALOG}.rls_demo.project_hours;
-- expected: 0, for EVERY caller including a workspace admin.
-- If this returns anything other than 0, the filter is not being applied and every result
-- above was meaningless.

-- Restore, and re-verify the original baseline before trusting anything.
CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.hours_group_filter(project_group STRING)
RETURN
    is_account_group_member('${GROUP_A}')
    OR (is_account_group_member('${GROUP_B}') AND project_group = 'water-delta');

SELECT count(*) FROM ${CATALOG}.rls_demo.project_hours;
-- expected: back to 7 / 3 / 0 depending on who is asking

-- ============================================================================================
-- 5. Isolate the MASK from the FILTER
-- ============================================================================================

-- A mask tested through a filter that already removes the row tells you nothing. So widen the
-- filter to admit everyone, leaving only the mask in play.

CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.hours_group_filter(project_group STRING)
RETURN TRUE;

SELECT entry_id, project_group, budget FROM ${CATALOG}.rls_demo.project_hours ORDER BY entry_id;
-- GROUP_A member : 7 rows, budget populated
-- anyone else    : 7 rows, budget NULL   <-- the mask, isolated

-- Restore again.
CREATE OR REPLACE FUNCTION ${CATALOG}.rls_demo.hours_group_filter(project_group STRING)
RETURN
    is_account_group_member('${GROUP_A}')
    OR (is_account_group_member('${GROUP_B}') AND project_group = 'water-delta');

-- ============================================================================================
-- 6. Who actually ran it
-- ============================================================================================

-- The independent check. Do not take the query result's word for whose permissions applied --
-- ask the platform. On a correctly-behaving OBO path, both columns name the HUMAN, not the
-- serving endpoint's service principal.
--
--   GET /api/2.0/sql/history/queries
--   (note: POST returns ENDPOINT_NOT_FOUND -- the working form is GET)
--
-- Compare `user_name` and `executed_as_user_name` for your statement id.

-- ============================================================================================
-- 7. A membership warning before you interpret any of this
-- ============================================================================================

-- Group nesting will mislead you. A workspace-local group can have an Entra-sourced group as a
-- MEMBER, so:
--
--   * everyone in the nested group is a TRANSITIVE member of the outer one
--   * removing someone from the outer group does NOT demote them -- they inherit it back
--   * Entra-sourced members do not enumerate over SCIM, and is_account_group_member() only
--     evaluates for the CALLING user
--
-- So there is no API read that answers "is this person in that group?". Check it from a query
-- they run themselves:

SELECT
    current_user()                            AS whoami,
    is_account_group_member('${GROUP_A}')     AS in_group_a,
    is_account_group_member('${GROUP_B}')     AS in_group_b;

-- ============================================================================================
-- Teardown
-- ============================================================================================

-- DROP SCHEMA ${CATALOG}.rls_demo CASCADE;
