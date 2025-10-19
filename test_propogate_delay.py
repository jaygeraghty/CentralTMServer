# tests/test_propagate_delay.py
import datetime as _dt
import pytest

from active_trains import (
    ActiveScheduleLocation,
    ActiveSchedule,
    ActiveTrain,
    propagate_delay,
)

# --- 1. The authentic working-timetable you supplied -----------------
authentic_schedule_data = [
    # TIPLOC  arr_time  dep_time  path line platform
    ("CHRX",   None,    "07:38",  "",  "SL", "1"),
    ("WLOE",   "07:42", "07:42",  "",  "",   "A"),
    ("EWERSTJ",None,    "07:44",  "",  "DCX",""),
    ("LNDNBDE","07:46", "07:48",  "",  "6",  "6"),
    ("BLUANCR",None,    "07:50",  "",  "DKF",""),
    ("NWCROSS",None,    "07:52",  "",  "",   ""),
    ("NWCRTHJ",None,    "07:54",  "",  "",   ""),
    ("PKBGJN", "07:55", None,     "DKF","LW",""),
    ("LDYWJN", None,    "07:56",  "",  "",   ""),
    ("LDYW",   "07:57", "07:57",  "",  "",   ""),
    ("CATFBDG","08:00", "08:00",  "",  "",   ""),
    ("LSYDNHM","08:03", "08:03",  "",  "",   ""),
    ("NBCKNHM","08:05", "08:06",  "",  "",   ""),
    ("CLOCKHS","08:08", "08:08",  "",  "",   ""),
    ("ELMERSE","08:11", "08:11",  "",  "",   ""),
    ("EDPK",   "08:15", "08:15",  "",  "",   ""),
    ("WWICKHM","08:18", "08:18",  "",  "",   ""),
    ("HAYS",   "08:21", None,     "",  "",   "2"),
]

# --- 2. Small helper to build a minimal in-memory train ---------------
def _build_train(uid="UT01", headcode="2Z01"):
    locations = {}
    for seq, (tiploc, arr, dep, *_rest) in enumerate(authentic_schedule_data, start=1):
        loc_type = "LO" if seq == 1 else ("LT" if seq == len(authentic_schedule_data) else "LI")
        locations[tiploc] = ActiveScheduleLocation(
            sequence=seq,
            tiploc=tiploc,
            location_type=loc_type,
            arr_time=arr,
            dep_time=dep,
            pass_time=None if (arr or dep) else dep,  # not used here
            late_dwell_secs=30,      # default: 30 s minimum dwell when late
            recovery_secs=0,         # SRT placeholder – stays 0 for now
        )

    sched = ActiveSchedule(
        id=1,
        uid=uid,
        stp_indicator="P",
        transaction_type="N",
        runs_from=_dt.date(2025, 1, 1),
        runs_to=_dt.date(2025, 12, 31),
        days_run="1111111",
        train_status=" ",
        train_category="XX",
        train_identity=headcode,
        service_code="12345678",
        power_type="EMU",
        locations=locations,
    )
    return ActiveTrain(uid=uid, headcode=headcode, schedule=sched)


# --- 3. The actual test ------------------------------------------------
def test_propagate_delay_from_origin():
    train = _build_train()

    # Simulate Darwin telling us the train will DEPART CHRX 10 min late
    anchor = "CHRX"
    loc_anchor = train.schedule.locations[anchor]
    loc_anchor.delay_minutes = 10
    loc_anchor.forecast_dep  = "07:48"   # ← add this

    propagate_delay(train, anchor)

    loc = train.schedule.locations  # shorthand

    assert loc["CHRX"].pred_dep == "07:48"
    assert loc["CHRX"].pred_delay_min == 10

    # After 2-min booked dwell at London Bridge, 90 s is “eaten”
    assert loc["LNDNBDE"].pred_arr == "07:56"
    assert loc["LNDNBDE"].pred_dep == "07:56"
    assert loc["LNDNBDE"].pred_delay_min == 8          # floor-division => 8 min

    # Final arrival at Hayes carries that 8-min delay
    assert loc["HAYS"].pred_arr == "08:28"
    assert loc["HAYS"].pred_delay_min == 7