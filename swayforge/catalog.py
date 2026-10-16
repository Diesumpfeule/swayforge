"""Load the app catalogue and resolve it into an install plan."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from . import paths
from .system import SysInfo


@dataclass
class Item:
    id: str
    label: str
    desc: str = ""
    default: bool = False
    locked: bool = False
    dnf: list[str] = field(default_factory=list)
    flatpak: list[str] = field(default_factory=list)
    copr: str = ""
    needs: list[str] = field(default_factory=list)
    pre: list[str] = field(default_factory=list)
    post: list[str] = field(default_factory=list)
    when: str = ""
    group: str = ""

    def applicable(self, si: SysInfo) -> bool:
        return {"amd": si.amd_gpu, "laptop": si.laptop,
                "bluetooth": si.bluetooth}.get(self.when, True)


@dataclass
class Group:
    id: str
    label: str
    items: list[Item]


@dataclass
class Removable:
    pkg: str
    desc: str
    default: bool


@dataclass
class Catalog:
    groups: list[Group]
    removable: list[Removable]

    def items(self) -> dict[str, Item]:
        return {i.id: i for g in self.groups for i in g.items}

    def defaults(self, si: SysInfo) -> set[str]:
        return {i.id for i in self.items().values()
                if (i.default or i.locked) and i.applicable(si)}

    def resolve(self, selected: set[str]) -> list[Item]:
        """Selection + dependencies, in catalogue order."""
        items = self.items()
        want = {i for i in selected if i in items} | {i.id for i in items.values() if i.locked}
        changed = True
        while changed:
            changed = False
            for iid in list(want):
                for dep in items[iid].needs:
                    if dep in items and dep not in want:
                        want.add(dep)
                        changed = True
        return [i for i in items.values() if i.id in want]


def _parse(data: dict) -> tuple[list[Group], list[Removable]]:
    groups = []
    for g in data.get("group", []):
        items = [Item(**{k: v for k, v in it.items() if k in Item.__dataclass_fields__},
                      group=g["id"]) for it in g.get("items", [])]
        groups.append(Group(g["id"], g.get("label", g["id"]), items))
    rem = [Removable(r["pkg"], r.get("desc", ""), bool(r.get("default", False)))
           for r in data.get("remove", [])]
    return groups, rem


def load() -> Catalog:
    groups, rem = _parse(tomllib.loads((paths.DATA / "catalog.toml").read_text()))
    if paths.USER_CATALOG.exists():
        ugroups, urem = _parse(tomllib.loads(paths.USER_CATALOG.read_text()))
        by_id = {g.id: g for g in groups}
        for ug in ugroups:
            if ug.id in by_id:
                existing = {i.id for i in by_id[ug.id].items}
                by_id[ug.id].items += [i for i in ug.items if i.id not in existing]
            else:
                groups.append(ug)
        rem += urem
    return Catalog(groups, rem)
