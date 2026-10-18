#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the exact reviewed Android ROM for --rom-dir; never access a device."""
import argparse
import importlib.util
from pathlib import Path


def load_stock():
    here = Path(__file__).resolve().parent
    path = here / 'lib/stock-rom.py'
    if not path.is_file():
        path = here / 'stock-rom.py'
    spec = importlib.util.spec_from_file_location('stock_rom', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True, help='Downloaded original ZIP, unchanged')
    parser.add_argument('--out', type=Path, required=True, help='New normalized ROM directory')
    args = parser.parse_args()
    stock = load_stock()
    stock.unpack_rom(args.archive.resolve(), args.out.resolve() / 'images')
    print('Verified ROM ready: ' + str(args.out.resolve()))
    print('Use this directory with --rom-dir. No tablet has been accessed.')


if __name__ == '__main__':
    main()
