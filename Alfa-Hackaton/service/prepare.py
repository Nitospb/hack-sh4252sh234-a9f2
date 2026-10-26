"""Prepare only online context/OCR assets. Does not scrape or train."""
import argparse
from pathlib import Path
from .context import build_profiles
from .bank import build, schema
import sqlite3

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='pipeline/output/service-assets.sqlite');p.add_argument('--csv');p.add_argument('--relationships');p.add_argument('--reports');p.add_argument('--tessdata');p.add_argument('--skip-ocr',action='store_true');a=p.parse_args()
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    build_profiles(out,a.csv,a.relationships)
    with sqlite3.connect(out) as db:schema(db)
    if not a.skip_ocr:build(out,a.reports,a.tessdata)
if __name__=='__main__':main()
