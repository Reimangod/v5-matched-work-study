from __future__ import annotations

import pytest

from v5_final import s11_v1_controlled_termination_item028_v1 as subject


def _rows(command: str = subject.EXPECTED_COMMAND):
    return [
        {
            "pid": subject.PPID,
            "ppid": 1,
            "pgid": subject.PGID,
            "launch_time": subject.EXPECTED_LAUNCH,
            "elapsed": "01-00:00:00",
            "cpu_percent": 0.0,
            "rss_kib": 100,
            "state": "S",
            "command": "rtk env " + subject.EXPECTED_COMMAND,
        },
        {
            "pid": subject.PID,
            "ppid": subject.PPID,
            "pgid": subject.PGID,
            "launch_time": subject.EXPECTED_LAUNCH,
            "elapsed": "01-00:00:00",
            "cpu_percent": 99.0,
            "rss_kib": 100,
            "state": "R",
            "command": command,
        },
    ]


def test_exact_identity_accepts_only_bound_process_group():
    result = subject.discover_exact_process(_rows())
    assert all(result["checks"].values())
    assert [row["pid"] for row in result["group_members"]] == [subject.PPID, subject.PID]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows[1].update(command="python unrelated.py"),
        lambda rows: rows[1].update(ppid=1),
        lambda rows: rows[1].update(pgid=999),
        lambda rows: rows[1].update(launch_time="Fri Aug 14 14:30:08 2026"),
        lambda rows: rows.append({**rows[1], "pid": 99999}),
    ],
)
def test_identity_drift_fails_closed(mutation):
    rows = _rows()
    mutation(rows)
    with pytest.raises(subject.ControlledTerminationError):
        subject.discover_exact_process(rows)


def test_reason_is_not_scientific_terminal():
    assert subject.REASON == "CONTROLLED_TERMINATION_UNBOUNDED_DENSE_UNITARY_VERIFICATION_COST"
    assert "REJECTION" not in subject.REASON
