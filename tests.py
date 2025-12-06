#!/usr/bin/env python3

from datetime import datetime, timedelta, UTC
import os
import unittest

from minitz import TZ, conv_to_tz


class ParseTests(unittest.TestCase):
    def test_utc(self):
        for variant in ['UTC0', 'UTC+0', 'UTC-00:00:00']:
            with self.subTest(f"Variant {variant}"):
                tz = TZ(variant)
                self.assertEqual(tz.tzname(None), "UTC")
                self.assertEqual(tz._utc_off.total_seconds(), 0)
                self.assertIsNone(tz._dst)

    def test_brackets(self):
        tz = TZ("<+03>+3")
        self.assertEqual(tz.tzname(None), "+03")

    def test_invalid_def(self):
        with self.assertRaises(ValueError):
            TZ("AAAA")

    def test_invalid_offset(self):
        with self.assertRaises(ValueError):
            TZ("XXX--0")

    def test_invalid_transition(self):
        with self.assertRaisesRegex(ValueError, "Invalid transition day"):
            TZ("XXX+2YYY,M.0.0,M2.1.0")

    def test_dst_behind_std(self):
        with self.assertRaisesRegex(ValueError, "DST needs to be ahead of STD"):
            TZ("XXX+2YYY+3,M1.1.0,M2.1.0")


class SimpleConversionTests(unittest.TestCase):
    def test_conv_std_offsets(self):
        tz1 = TZ("AAA+2")
        tz2 = TZ("BBB+3")

        dt1 = datetime(2025, 12, 6, 16, 35, 42, tzinfo=tz1)
        dt2 = datetime(2025, 12, 6, 15, 35, 42, tzinfo=tz2)

        self.assertEqual(dt1.astimezone(tz2), dt2)

    def test_conv_func(self):
        tz1 = TZ("AAA+2")
        tz2 = TZ("BBB+3")

        dt1 = datetime(2025, 12, 6, 16, 35, 42, tzinfo=tz1)
        dt2 = datetime(2025, 12, 6, 15, 35, 42, tzinfo=tz2)

        self.assertEqual(conv_to_tz(dt1, tz2), dt2)
        self.assertIs(conv_to_tz(dt1, tz1), dt1)

    def test_reject_naive_conv(self):
        tz = TZ("AAA+2")
        dt1 = datetime(2025, 12, 6, 16, 35, 42, tzinfo=None)
        dt2 = datetime(2025, 12, 6, 16, 35, 42, tzinfo=tz)

        with self.assertRaises(ValueError):
            conv_to_tz(dt1, tz)

        with self.assertRaises(ValueError):
            conv_to_tz(dt2, None)


class DSTSwitchoverTests(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        super().__init__(methodName=methodName)
        self._verbose = False

    def run(self, result):
        self._verbose = result.showAll
        super().run(result)

    def test_ce_switchover(self):
        # Northern hemisphere, DST starts early in the year and stops late in
        # the year
        # DST start at 2 (=> 3), ends at 3 (=> 2)
        #ce = zoneinfo.ZoneInfo("Europe/Paris")
        ce = TZ("CET-1CEST,M3.5.0,M10.5.0/3")

        self._test_dst_start(ce, 2025, 3, 30, 2, 1, 1, "CET", "CEST")
        self._test_dst_end(ce, 2025, 10, 26, 3, 1, 1, "CET", "CEST")

    def test_nz_switchover(self):
        # Southern hemisphere, DST ends early in the year and starts late in the
        # year
        # DST start at 2 (=> 3), ends at 3 (=> 2)
        #nz = zoneinfo.ZoneInfo("NZ")
        nz = TZ("NZST-12NZDT,M9.5.0,M4.1.0/3")

        self._test_dst_end(nz, 2025, 4, 6, 3, 12, 1, "NZST", "NZDT")
        self._test_dst_start(nz, 2025, 9, 28, 2, 12, 1, "NZST", "NZDT")

    def test_non_existent_hour(self):
        ce = TZ("CET-1CEST,M3.5.0,M10.5.0/3")

        # After 01:59:59 comes 03:00:00; 02:00:00 is invalid but treated as if
        # it were 03:00:00
        invalid1 = datetime(2025, 3, 30, 2, 0, 0, tzinfo=ce)
        expected1 = datetime(2025, 3, 30, 3, 0, 0, tzinfo=ce)

        self.assertEqual(invalid1.astimezone(UTC), expected1.astimezone(UTC))

        # But if the fold is set, it is treated as if it were 01:00:00
        invalid2 = datetime(2025, 3, 30, 2, 0, 0, tzinfo=ce, fold=1)
        expected2 = datetime(2025, 3, 30, 1, 0, 0, tzinfo=ce)

        self.assertEqual(invalid2.astimezone(UTC), expected2.astimezone(UTC))



    def _test_dst_start(self, tz, year, month, day, hour, utc_offset,
        dst_adj, std_name, dst_name):

        if self._verbose:
            print("")

        std_offset = timedelta(hours=utc_offset)
        dst_offset = timedelta(hours=utc_offset + dst_adj)

        base = datetime(year, month, day, hour, 0, 0, 0)
        base_utc = base.replace(tzinfo=UTC) - timedelta(hours=utc_offset)

        with self.subTest("One hour before"):
            local = (base - timedelta(hours=1)).replace(tzinfo=tz)
            self.assertEqual(local.utcoffset(), std_offset)
            self.assertEqual(local.tzname(), std_name)
            utc = base_utc - timedelta(hours=1)
            self._check_conv(local, utc)

        with self.subTest("Just before"):
            local = (base - timedelta(seconds=1)).replace(tzinfo=tz)
            self.assertEqual(local.utcoffset(), std_offset)
            self.assertEqual(local.tzname(), std_name)
            utc = base_utc - timedelta(seconds=1)
            self._check_conv(local, utc)

        with self.subTest("At switchover"):
            # local gets dst_adj, utc gets nothing
            local = (base + timedelta(hours=dst_adj)).replace(tzinfo=tz)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)
            utc = base_utc
            self._check_conv(local, utc)

        with self.subTest("One hour after"):
            local = (base + timedelta(hours=dst_adj + 1)).replace(tzinfo=tz)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)
            utc = base_utc + timedelta(hours=1)
            self._check_conv(local, utc)

    def _test_dst_end(self, tz, year, month, day, hour, utc_offset,
        dst_adj, std_name, dst_name):

        if self._verbose:
            print("")

        std_offset = timedelta(hours=utc_offset)
        dst_offset = timedelta(hours=utc_offset + dst_adj)

        base = datetime(year, month, day, hour, 0, 0, 0)
        base -= timedelta(hours=dst_adj)
        base_utc = base.replace(tzinfo=UTC) - timedelta(hours=utc_offset)

        with self.subTest("One hour before first crossing"):
            local = (base - timedelta(hours=1)).replace(tzinfo=tz)
            utc = base_utc - timedelta(hours=1 + dst_adj)
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)

        with self.subTest("Just before first crossing"):
            local = (base - timedelta(seconds=1)).replace(tzinfo=tz)
            utc = base_utc - timedelta(hours=dst_adj, seconds=1)
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)

        with self.subTest("At first crossing"):
            local = base.replace(tzinfo=tz)
            utc = base_utc - timedelta(hours=dst_adj)
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)

        with self.subTest("Just before second crossing"):
            offset = timedelta(hours=dst_adj, seconds=-1)
            local = (base + offset).replace(tzinfo=tz)
            utc = base_utc + offset + timedelta(hours=-dst_adj)
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), dst_offset)
            self.assertEqual(local.tzname(), dst_name)

        with self.subTest("At second crossing"):
            offset = timedelta(hours=dst_adj)
            # Local is like at first crossing but with fold=1
            local = base.replace(tzinfo=tz, fold=1)

            utc = base_utc + offset + timedelta(hours=-dst_adj)
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), std_offset)
            self.assertEqual(local.tzname(), std_name)

        with self.subTest("Near end of repeated interval"):
            offset = timedelta(hours=dst_adj, seconds=-1)
            local = (base + offset).replace(tzinfo=tz, fold=1)
            utc = base_utc + offset
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), std_offset)
            self.assertEqual(local.tzname(), std_name)

        with self.subTest("End of repeated interval"):
            offset = timedelta(hours=dst_adj)
            local = (base + offset).replace(tzinfo=tz)
            utc = base_utc + offset
            self._check_conv(local, utc)
            self.assertEqual(local.utcoffset(), std_offset)
            self.assertEqual(local.tzname(), std_name)

    def _check_conv(self, local, utc):
        self.longMessage = False

        to_utc = local.astimezone(UTC)

        if self._verbose:
            print(f"{local} ({local.fold}) => {to_utc} <=> {utc}")

        self.assertEqual(to_utc, utc)

        to_local = utc.astimezone(local.tzinfo)
        self.assertEqual(to_local, local, f"CONV UTC {to_utc} expected {local} "
            f"({local.fold}) got {to_local} ({to_local.fold})")


if __name__ == '__main__':
    unittest.main(verbosity=2)
