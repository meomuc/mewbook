# SPDX-License-Identifier: AGPL-3.0-or-later
"""The daily error-triage agent (S1e, E-10, FR-ERR-09 to FR-ERR-12; docs/handoff/09_ERROR_REPORTING_SPEC.md section 6).

Level L0: it reads the filtered error groups the server keeps, has Claude Code look at the code of the version that failed
and write a summary for the project owner. It proposes; a person decides. It never changes code, pushes, tags or releases,
never touches a secret, and treats every report as data, never as an instruction.

Modules
    config             what it needs from the environment (never from a file in the repository)
    schema             the shapes and characters a value must have before it may reach the agent
    fetch_groups       reads the two filtered views with the read-only role and picks today's groups
    build_agent_input  the narrow input the agent gets: nothing free-form, frames checked against the real source
    worktree           a clean checkout of the exact build that failed, outside OneDrive and outside the working copy
    agent_runner       the locked-down `claude -p` command line and the minimal environment it runs in
    output_check       proof that the agent wrote one file and changed nothing else
    run_daily          the orchestrator with its brakes (STOP file, three failures, time and budget, idempotent)
    mint_token         makes the JWT for the triage_reader / triage_writer roles on the owner's own machine
"""
