import importlib.util
import pathlib
import tempfile
import unittest

SRC = pathlib.Path(__file__).parents[1] / "rootfs/usr/local/bin/attempt_limit.py"
spec = importlib.util.spec_from_file_location("attempt_limit", SRC)
al = importlib.util.module_from_spec(spec)
spec.loader.exec_module(al)

NOW = 1_763_280_000.0
DAY = 86400


class LimitTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.f = str(pathlib.Path(self.dir.name) / "attempts")

    def tearDown(self):
        self.dir.cleanup()

    def check(self, now=NOW):
        return al.main(["x", "check", self.f, "3", str(DAY), "600"], now=now)

    def record(self, now=NOW):
        return al.main(["x", "record", self.f, str(DAY)], now=now)

    def test_ohne_datei_ist_erlaubt(self):
        self.assertEqual(self.check(), 0)

    def test_kaputte_datei_ist_erlaubt(self):
        pathlib.Path(self.f).write_text("kaputt\n")
        self.assertEqual(self.check(), 0)

    def test_mindestabstand(self):
        self.record(NOW)
        self.assertEqual(self.check(NOW + 599), 1)
        self.assertEqual(self.check(NOW + 601), 0)

    def test_maximal_drei_pro_tag(self):
        for i in range(3):
            self.record(NOW + i * 1000)
        self.assertEqual(self.check(NOW + 5000), 1)

    def test_nach_dem_zeitfenster_wieder_erlaubt(self):
        for i in range(3):
            self.record(NOW + i * 1000)
        self.assertEqual(self.check(NOW + DAY + 3000), 0)

    def test_alte_eintraege_werden_beim_vermerken_entfernt(self):
        self.record(NOW)
        self.record(NOW + 2 * DAY)
        self.assertEqual(len(pathlib.Path(self.f).read_text().split()), 1)

    def test_zukunftszeitstempel_zaehlen_nicht(self):
        pathlib.Path(self.f).write_text(f"{NOW + 10 * DAY:.0f}\n")
        self.assertEqual(self.check(), 0)

    def test_ungueltige_argumente(self):
        self.assertEqual(al.main(["x", "check", self.f, "drei", "1", "1"], now=NOW), 1)
        self.assertEqual(al.main(["x"], now=NOW), 1)


if __name__ == "__main__":
    unittest.main()
