"""
Miniature tzinfo implementation
"""

try:
    from datetime import datetime, date, timedelta, tzinfo
except ImportError:
    from adafruit_datetime import datetime, date, timedelta, tzinfo # type: ignore

import re

_TD = timedelta


class TZ(tzinfo):
    """
    Python tzinfo object from a timezone definition
    """

    # CircuitPython’s regex module cannot handle a complex regex that would
    # extract all fields in one go; use a main regex and field-specific
    # sub-regexes.
    _TZ_RE = re.compile(
        r'^'
        r'([A-Z]+|<[A-Z0-9+-]+>)' # std
        r'([0-9:+-]+)' # std offset
        r'(' # Optional DST/time part (non-capturing groups are not supported)
            r'([A-Z]+|<[A-Z0-9+-]+>)' # dst
            r'([0-9:+-]+)?' # optional dst offset
            r',M([0-9.]+)' # dst start day
            r'(/[0-9:+-]+)?' # optional dst start hour
            r',M([0-9.]+)' # dst end day
            r'(/[0-9:+-]+)?' # optional dst end hour
        r')?' # End of optional DST/time part
        r'$'
    )

    _TZ_OFF_RE = re.compile(r'([+-])?(\d\d?)(:(\d\d?)(:(\d\d?))?)?')

    def __init__(self, tz_def: str):
        match = self._TZ_RE.match(tz_def)
        if not match:
            raise ValueError(f"Invalid TZ definition {tz_def!r}")

        groups = match.groups()

        self._std = self._parse_tz_name(groups[0])

        # The tzset format use separate STD and DST offsets positive west of
        # UTC, while Python uses a DST offset negative west of UTC and a
        # DST adjustment.

        std_off = self._parse_offset(groups[1])
        self._utc_off = -std_off

        if groups[2] is None:
            # No DST definition
            self._dst = None
            return

        self._dst = self._parse_tz_name(groups[3])
        if groups[4] is None:
            # No DST offset, DST is one hour ahead of standard time
            self._dst_adj = timedelta(hours=1)
        else:
            # Get DST offset and calculate DST adjustment from it
            dst_off = self._parse_offset(groups[4])
            self._dst_adj = std_off - dst_off

        if self._dst_adj.total_seconds() <= 0:
            raise ValueError("DST needs to be ahead of STD")

        start_day, start_hour = self._parse_trans(groups[5], groups[6])
        self._start = self.DSTTransition(start_day, start_hour)

        end_day, end_hour = self._parse_trans(groups[7], groups[8])
        self._end = self.DSTTransition(end_day, end_hour)

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return self._utc_off + self.dst(dt)

    def dst(self, dt: datetime | None) -> timedelta:
        if self._is_local_dst(dt):
            return self._dst_adj

        return timedelta(0)

    def fromutc(self, dt: datetime) -> datetime:
        assert dt.tzinfo is self

        std_dt = dt + self._utc_off

        if self._dst is None:
            return std_dt

        year = dt.year
        dst_start = self._start.for_year(year).replace(tzinfo=self)
        dst_end = self._end.for_year(year).replace(tzinfo=self)

        return self._std_to_dst(std_dt, dst_start, dst_end)

    def tzname(self, dt: datetime | None) -> str:
        if self._dst is None or not self._is_local_dst(dt):
            return self._std

        return self._dst

    def _is_local_dst(self, dt: datetime | None) -> bool:
        """
        Calculates if a given local datetime is in DST.
        Returns False if dt is None or the timezone has no DST.
        """

        if dt is None or self._dst is None:
            return False

        dt = dt.replace(tzinfo=None)
        year = dt.year
        dst_start = self._start.for_year(year)
        dst_end = self._end.for_year(year)

        if dst_start <= dst_end:
            # Northern hemisphere: DST in middle of calendar year
            # First check if date is before DST start, then check if it’s before
            # DST end.
            res = self._chk_dst_start(dt, dst_start)
            if res is None:
                res = self._chk_dst_end(dt, dst_end)
            if res is None:
                res = False

        else:
            # Southern hemisphere: DT at start and end of calendar year
            # First check if date is before DST end, then check if it’s after
            # DST start.
            res = self._chk_dst_end(dt, dst_end)
            if res is None:
                res = self._chk_dst_start(dt, dst_start)
            if res is None:
                res = True

        return res

    def _chk_dst_start(self, dt: datetime, dst_start: datetime) -> bool | None:
        """
        Check if the datetime occurs before the DST start (returns False) or
        in the non-existent hour(s) (returns True or False depending on fold).
        If that’s not the case, returns None.
        """

        if dt < dst_start:
            # Not started yet
            return False

        if dt < dst_start + self._dst_adj:
            # Non-existent hour(s): do what the Python doc example say,
            # i.e. consider it DST if fold is set.
            return bool(dt.fold)

        return None

    def _chk_dst_end(self, dt: datetime, dst_end: datetime) -> bool | None:
        """
        Check if the datetime occurs before the DST end (returns True) or in
        the ambiguous hour(s) (returns True or False depending on fold).
        If that’s not the case, returns None.
        """

        if dt < dst_end - self._dst_adj:
            # Not ended yet
            return True

        if dt < dst_end:
            # Ambiguous hour(s): If fold is set, this is the second time the
            # hour occurred, so we are not in DST anymore.
            return not dt.fold

        return None

    def _std_to_dst(self, std_dt: datetime, dst_start: datetime,
        dst_end: datetime) -> datetime:
        """
        Adjust a STD datetime to DST if necessary, given the DST start and end
        datetime as local time.
        All provided datetimes should have tzinfo set to self.
        """

        # True in Northern hemisphere where DST is in middle of calendar year
        dst_middle_year = dst_start <= dst_end

        # Check DST start first only if DST in middle of year
        if dst_middle_year and std_dt < dst_start:
            # DST has not started yet
            return std_dt

        if std_dt < dst_end - self._dst_adj:
            # In DST (including first time in ambiguous zone)
            return std_dt + self._dst_adj

        if std_dt < dst_end:
            # In ambiguous zone, second time; not DST anymore but set the fold
            # for disambiguation
            return std_dt.replace(fold=1)

        if dst_middle_year:
            # Not in DST anymore
            return std_dt

        # Southern hemisphere: check for DST start after checking for DST end
        if std_dt < dst_start:
            # Not yet in second DST part of the year
            return std_dt

        # In DST part of the year
        return std_dt + self._dst_adj


    @staticmethod
    def _parse_tz_name(tz_def: str) -> str:
        """
        Parse a timezone name. The definition should be already validated
        (i.e. not None, either alphabetical or alphanumerical/+/- between <>)
        """

        if tz_def[0] == '<':
            return tz_def [1:-1]

        return tz_def

    @classmethod
    def _parse_offset(cls, off_def: str) -> _TD:
        """
        Parse an offset definition into a timedelta.
        """

        match = cls._TZ_OFF_RE.match(off_def)
        if not match:
            raise ValueError("Invalid offset {off_def!r}")

        sign_val, hours_val, _, mins_val, _, secs_val = match.groups()

        sign = -1 if sign_val == '-' else 1
        hours = int(hours_val, 10)
        mins = 0 if mins_val is None else int(mins_val, 10)
        secs = 0 if secs_val is None else int(secs_val, 10)

        return sign * timedelta(hours=hours, minutes=mins, seconds=secs)

    @classmethod
    def _parse_trans(cls, date_def: str, time_def: str | None) -> \
        tuple[tuple[int, int, int], _TD]:
        """
        Convert a transition day/time into a date definition and a timedelta.
        The day definition should be "<m>.<w>.<d>" (no negatives) and the
        time definition is either "/<offset>" or None.
        """

        try:
            date_vals = tuple(int(val, 10) for val in date_def.split('.'))
        except ValueError:
            date_vals = ()

        if len(date_vals) != 3:
            raise ValueError("Invalid transition day definition {date_def!r}")

        if time_def is None:
            time_val = timedelta(hours=2)
        else:
            time_val = cls._parse_offset(time_def[1:])

        return date_vals, time_val

    def __repr__(self) -> str:
        if self._dst:
            return (f"<{self._std} {self._utc_off}/{self._dst} adj "
                f"{self._dst_adj} start {self._start!r} end {self._end!r}")

        return f"<{self._std} {self._utc_off}>"

    class DSTTransition:
        """
        Calculates the date at which DST transition with occur.
        """

        def __init__(self, day_spec: tuple[int, int, int], hour: _TD):
            self._day_spec = day_spec
            self._hour = hour

        def for_year(self, year: int) -> datetime:
            """
            Calculates the DST transition for the specified year number,
            as a local naïve datetime.
            """

            month, week_num, day_num = self._day_spec

            # Day number (7 = Sunday, 1 = Monday) of the 1st of the target month
            day_num_first = date(year, month, 1).isoweekday()

            # Offset to first day_num of the month
            # day_num is 0 = Sunday, 1 = Monday, so it is the same as isoweekday
            # mod 7.
            first_day_num_off = (day_num + 7 - day_num_first) % 7

            day_off = first_day_num_off + (week_num - 1) * 7
            try:
                base_dt = datetime(year, month, 1 + day_off)
            except ValueError:
                base_dt = datetime(year, month, 1 + day_off - 7)

            return base_dt + self._hour

        def __repr__(self) -> str:
            month, week, day = self._day_spec
            return f"<{month}.{week}.{day} {self._hour}>"


UTC: TZ = TZ("UTC0")


def conv_to_tz(dt: datetime, tz: tzinfo) -> datetime:
    """
    Converts the datetime to the specified timezone.
    """

    utc_offset = dt.utcoffset()

    if utc_offset is None or tz is None:
        raise ValueError("Cannot convert from/to naive datetimes")

    if dt.tzinfo is tz:
        return dt

    utc = (dt - utc_offset).replace(tzinfo=tz)

    return tz.fromutc(utc)
