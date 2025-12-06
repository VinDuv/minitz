MiniTZ
======

MiniTZ is a small implementation of the Python datetime
[tzinfo](https://docs.python.org/library/datetime.html#datetime.tzinfo) class.

It can be used on embedded systems running
[CircuitPython](https://circuitpython.org) to calculate a local time from an UTC
time, taking DST into consideration.

Usage
-----

Call `minitz.TZ("<TZ definition>")` to get a `tzinfo` object representing
the specified time zone definition. This definition corresponds to the TZ format
specified by [https://man7.org/linux/man-pages/man3/tzset.3.html](tzset):

```
std offset[dst[offset][,start[/time],end[/time]]]
```

See the manual page for more details. You can find the TZ definition for your
timezone by looking at the very last line of the file in `/usr/share/zoneinfo`
corresponding to your timezone.

Note that DST start and end time can only be specified in `Mm.w.d` format;
Julian day formats are not currently supported.

The created `tzinfo` object then provides the `utcoffset`, `dst`, `tzname` and
`fromutc` methods as described in the Python documentation.

The implementation correctly handles the `fold` flag used to disambiguates
datetimes during DST to STD transition. It also handles DST in the Southern
hemisphere, where DST end is before DST start.

As a convenience, the `minitz` module also provides a `UTC` object to represent
a UTC timestamp, and a `conv_to_tz` method which, when called on a datetime
`dt`, performs the equivalent of `dt.astimezone(tzinfo)` (i.e. converts the 
datetime from its tzinfo to the specified tzinfo). This can be used in
CircuitPython which does not implement this method.