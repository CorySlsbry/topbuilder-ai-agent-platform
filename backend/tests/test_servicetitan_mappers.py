"""Unit tests for the ServiceTitan response mappers (the transformation logic)."""
from __future__ import annotations

from datetime import date

from app.integrations.servicetitan.mappers import map_appointment, map_timesheet


class TestMapAppointment:
    def test_duration_in_hours_and_fields(self) -> None:
        row = {
            "id": 123,
            "jobId": 456,
            "start": "2026-06-10T08:00:00Z",
            "end": "2026-06-10T11:30:00Z",
            "technicianId": "t-9",
            "jobType": "ac_repair",
            "trade": "hvac",
            "status": "scheduled",
        }
        appt = map_appointment(row)
        assert appt.id == "123"
        assert appt.job_id == "456"
        assert appt.trade == "hvac"
        assert appt.appt_date == date(2026, 6, 10)
        assert appt.scheduled_hours == 3.5  # 08:00 -> 11:30
        assert appt.technician_id == "t-9"

    def test_unassigned_and_defaults(self) -> None:
        row = {"id": 1, "start": "2026-06-10T08:00:00+00:00", "end": "2026-06-10T09:00:00+00:00"}
        appt = map_appointment(row)
        assert appt.technician_id is None
        assert appt.scheduled_hours == 1.0
        assert appt.trade == "unknown"


class TestMapTimesheet:
    def test_fields(self) -> None:
        row = {"technicianId": "t-1", "date": "2026-06-09", "regularHours": 38, "overtimeHours": 2.5}
        ts = map_timesheet(row)
        assert ts.technician_id == "t-1"
        assert ts.work_date == date(2026, 6, 9)
        assert ts.regular_hours == 38.0
        assert ts.overtime_hours == 2.5
