# Restore the default Trash sweep on util-linux

Task: disk-cleanup-findmnt
Owner: maintainer
Approved: 2026-11-27

## Approved scope

Fix the existing disk-cleanup script so it can enumerate mount targets and apply its existing Trash safety checks on util-linux. Preserve the cleanup policy and weekly schedule.
