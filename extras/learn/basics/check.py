"""Tiny helper for the exercises. You never need to edit this file."""


def check(name, got, expected):
    if got == expected:
        print(f"  OK   {name}")
    else:
        print(f"  NOPE {name}: expected {expected!r}, got {got!r}")
