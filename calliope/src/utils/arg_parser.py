import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    "-v",
    "--verbose",
    type=bool,
    default=False,
    help="Set it to True to enable verbose mode",
)
args = parser.parse_args()
