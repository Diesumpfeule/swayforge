"""The wiper can never reach the system disk – checked with a fake /sys, /proc and /dev only."""
import os
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts the repo on sys.path)
from swayforge import cleanup


def fake_machine():
    """nvme0n1 = system (p1 EFI, p2 LUKS → dm-0 btrfs / and /home), nvme1n1 = Windows drive (internal,
    'hotplug'), sda = USB stick, sdb = USB disk with a swayforge fstab mount, sdc = USB swap."""
    r = Path(tempfile.mkdtemp())
    sysb = r / "sys/class/block"
    devs = r / "sys/devices"
    sysb.mkdir(parents=True)

    def disk(name, parts=()):
        d = devs / name
        d.mkdir(parents=True)
        os.symlink(d, sysb / name)
        for p in parts:
            (d / p).mkdir()
            (d / p / "partition").write_text("1")
            os.symlink(d / p, sysb / p)

    disk("nvme0n1", ["nvme0n1p1", "nvme0n1p2"])
    disk("nvme1n1", ["nvme1n1p1"])
    disk("sda", ["sda1"])
    disk("sdb", ["sdb1"])
    disk("sdc", ["sdc1"])
    (devs / "dm-0/slaves").mkdir(parents=True)
    os.symlink(devs / "dm-0", sysb / "dm-0")
    os.symlink(sysb / "nvme0n1p2", devs / "dm-0/slaves/nvme0n1p2")
    dev = r / "dev"
    (dev / "mapper").mkdir(parents=True)
    (dev / "disk/by-uuid").mkdir(parents=True)
    for n in ("nvme0n1", "nvme0n1p1", "nvme0n1p2", "nvme1n1", "nvme1n1p1", "sda", "sda1", "sdb", "sdb1",
              "sdc", "sdc1", "dm-0"):
        (dev / n).write_text("")
    os.symlink(dev / "dm-0", dev / "mapper/luks-root")
    os.symlink(dev / "sdb1", dev / "disk/by-uuid/DATA-1")
    proc = r / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self/mounts").write_text("/dev/mapper/luks-root / btrfs rw 0 0\n/dev/mapper/luks-root /home btrfs rw 0 0\n"
                                      "/dev/nvme0n1p1 /boot/efi vfat rw 0 0\ntmpfs /tmp tmpfs rw 0 0\n")
    (proc / "swaps").write_text("Filename Type Size Used Priority\n/dev/sdc1 partition 1 0 -2\n/dev/zram0 partition 1 0 100\n")
    (r / "fstab").write_text("# comment\nUUID=DATA-1 /mnt/data ext4 nofail 0 2\n")
    return r


def lsblk(name, tran, size=32_000_000_000, rm=False, hotplug=False, children=()):
    return {"name": name, "path": f"/dev/{name}", "type": "disk", "tran": tran, "rm": rm, "hotplug": hotplug,
            "size": size, "children": [dict(c, type="part") for c in children], "serial": "S" + name}


class SystemDisk(unittest.TestCase):
    def setUp(self):
        r = fake_machine()
        self.sysdisks = cleanup.system_disks(sys_root=str(r / "sys"), proc_root=str(r / "proc"),
                                             fstab=str(r / "fstab"), dev_root=str(r / "dev"))

    def test_kernel_view_finds_everything_in_use(self):
        self.assertIn("nvme0n1", self.sysdisks, "root through LUKS/dm")
        self.assertIn("sdb", self.sysdisks, "fstab entry by UUID")
        self.assertIn("sdc", self.sysdisks, "active swap")
        self.assertNotIn("sda", self.sysdisks)

    def test_only_the_free_usb_stick_is_offered(self):
        devs = [
            # system disk even if lsblk claimed it was USB and showed no mount points
            lsblk("nvme0n1", "usb", children=[{"name": "nvme0n1p2", "fstype": "crypto_LUKS"}]),
            lsblk("nvme1n1", "nvme", hotplug=True, children=[{"name": "nvme1n1p1", "fstype": "ntfs"}]),
            lsblk("sda", "usb", children=[{"name": "sda1", "fstype": "exfat"}]),
            lsblk("sdb", "usb", children=[{"name": "sdb1", "fstype": "ext4"}]),
            lsblk("sdc", "usb", children=[{"name": "sdc1", "fstype": "swap"}]),
            lsblk("sdd", "sata", rm=True),
            lsblk("mmcblk0", "mmc", size=0),
        ]
        self.assertEqual([d["name"] for d in cleanup.drives_from(devs, self.sysdisks)], ["sda"])

    def test_reasons(self):
        self.assertIn("internal", cleanup.refuse_reason(lsblk("nvme1n1", "nvme", hotplug=True), self.sysdisks))
        self.assertIn("fstab", cleanup.refuse_reason(lsblk("sdb", "usb"), self.sysdisks))
        self.assertIn("running system", cleanup.refuse_reason(
            lsblk("sde", "usb", children=[{"name": "sde1", "mountpoints": ["/"]}]), set()))

    def test_wipe_refuses_unknown_and_swapped_drives(self):
        orig = cleanup.wipeable_drives
        try:
            cleanup.wipeable_drives = lambda: []
            self.assertEqual(cleanup.wipe_main("nvme0n1", "quick", "exfat", "X", 0, "nvme0n1"), 1)
            stick = cleanup.drives_from([lsblk("sda", "usb")], set())
            cleanup.wipeable_drives = lambda: stick
            self.assertEqual(cleanup.wipe_main("sda", "quick", "exfat", "X", 0, "sda", serial="OTHER"), 1)
            self.assertEqual(cleanup.wipe_main("sda", "quick", "exfat", "X", 1, "sda"), 1)
            self.assertEqual(cleanup.wipe_main("sda", "quick", "exfat", "X", 0, "wrong"), 1)
        finally:
            cleanup.wipeable_drives = orig


if __name__ == "__main__":
    unittest.main()
