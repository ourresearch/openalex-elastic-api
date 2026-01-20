# -*- coding: utf-8 -*-

DESCRIPTION = """for all works in elasticsearch, export the work id and the url for the locations"""

import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from timeit import default_timer as timer

try:
    from humanfriendly import format_timespan
except ImportError:

    def format_timespan(seconds):
        return "{:.2f} seconds".format(seconds)


import logging

root_logger = logging.getLogger()
logger = root_logger.getChild(__name__)

from elasticsearch_dsl import Q, Search, connections

from settings import ES_URL_WALDEN, WORKS_INDEX_LEGACY


def get_ids():
    s = Search(index=WORKS_INDEX_LEGACY)
    s = s.source(["id", "locations.landing_page_url"])
    count_works = 0
    count_lines = 0
    outfp = Path("location_urls_from_elasticsearch.txt")
    logger.info(f"opening file for write: {outfp}")
    with outfp.open("w", newline="") as outf:
        writer = csv.writer(outf)
        for h in s.scan():
            if "locations" in h and h["locations"]:
                id_numerical_part = h["id"].replace("https://openalex.org/W", "")
                try:
                    int(id_numerical_part)
                except ValueError:
                    logger.warning(f"malformed id found: {h['id']}. skipping")
                    continue
                for location in h["locations"]:
                    writer.writerow([id_numerical_part, location["landing_page_url"]])
                    count_lines += 1
                    if (
                        count_lines
                        in [100, 1000, 10000, 100000, 500000, 1000000, 5000000]
                        or count_lines % 10000000 == 0
                    ):
                        logger.info(f"{count_lines} rows written ({count_works} works)")
                count_works += 1
            else:
                logger.warning(f"no locations found for work {h['id']}")
    logger.info(f"done. {count_lines} lines written for {count_works} works")


def main(args):
    connections.create_connection(hosts=[ES_URL_WALDEN], timeout=600)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    get_ids()


if __name__ == "__main__":
    total_start = timer()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(name)s.%(lineno)d %(levelname)s : %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    logger.info(" ".join(sys.argv))
    logger.info("{:%Y-%m-%d %H:%M:%S}".format(datetime.now()))
    logger.info("pid: {}".format(os.getpid()))
    import argparse

    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--debug", action="store_true", help="output debugging info")
    global args
    args = parser.parse_args()
    if args.debug:
        root_logger.setLevel(logging.DEBUG)
        logger.debug("debug mode is on")
    main(args)
    total_end = timer()
    logger.info(
        "all finished. total time: {}".format(format_timespan(total_end - total_start))
    )
