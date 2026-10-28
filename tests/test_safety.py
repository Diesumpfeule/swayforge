"""Backups never write outside HOME; the updater never loses your own changes."""
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, fresh_home


class BackupImport(unittest.TestCase):
    def test_hostile_archive_stays_inside_home(self):
        home = fresh_home()
        from swayforge import tools
        evil = Path(tempfile.mkdtemp()) / "evil.tar.gz"
        outside = Path(tempfile.mkdtemp()) / "pwned"
        with tarfile.open(evil, "w:gz") as tar:
            for name, data in ((f"../{outside.parent.name}/pwned", b"x"), (str(outside), b"x"),
                               (".config/swayforge/settings.toml", b'[look]\nradius = 2\n')):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo(".config/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tar.addfile(link)
        self.assertEqual(tools.import_(str(evil)), 0)
        self.assertFalse(outside.exists())
        self.assertFalse((home / ".config/link").exists())
        self.assertTrue((home / ".config/swayforge/settings.toml").exists())

    def test_export_round_trip(self):
        home = fresh_home()
        from swayforge import paths, settings, tools
        paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        settings.save(settings.load())
        out = home / "b.tar.gz"
        self.assertEqual(tools.export(str(out)), 0)
        with tarfile.open(out) as tar:
            self.assertIn(".config/swayforge/settings.toml", tar.getnames())


@unittest.skipUnless(shutil.which("git"), "git missing")
class Updater(unittest.TestCase):
    def git(self, *a, cwd):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                       capture_output=True)

    def test_local_changes_are_stashed_not_lost(self):
        from swayforge import update
        base = Path(tempfile.mkdtemp())
        origin, clone = base / "origin", base / "clone"
        origin.mkdir()
        self.git("init", "-q", "-b", "main", cwd=origin)
        (origin / "lesson.py").write_text("v1\n")
        self.git("add", ".", cwd=origin)
        self.git("commit", "-qm", "one", cwd=origin)
        self.git("clone", "-q", str(origin), str(clone), cwd=base)
        (clone / "lesson.py").write_text("my own work\n")                  # you edited it …
        (origin / "lesson.py").unlink()                                     # … and upstream removed it
        (origin / "new.py").write_text("new\n")
        self.git("add", "-A", cwd=origin)
        self.git("commit", "-qm", "two", cwd=origin)
        r = subprocess.run(["bash", "-c", update.pull_cmd("test", f"'{clone}'")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((clone / "new.py").exists(), "updated to the new version")
        stash = subprocess.run(["git", "-C", str(clone), "stash", "list"], capture_output=True, text=True).stdout
        self.assertIn("before update", stash, "your change is kept in the stash")


class Install(unittest.TestCase):
    def test_install_script_syntax(self):
        for sh in [ROOT / "install.sh", *ROOT.glob("extras/*/*.sh")]:
            with self.subTest(script=sh.name):
                r = subprocess.run(["bash", "-n", str(sh)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)


class Atomic(unittest.TestCase):
    def test_atomic_write_keeps_mode_and_leaves_no_temp(self):
        from swayforge.fsutil import atomic_write
        d = Path(tempfile.mkdtemp())
        f = d / "x.sh"
        f.write_text("old")
        os.chmod(f, 0o755)
        atomic_write(f, "new")
        self.assertEqual(f.read_text(), "new")
        self.assertEqual(f.stat().st_mode & 0o777, 0o755)
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["x.sh"])


if __name__ == "__main__":
    unittest.main()
