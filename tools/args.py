import argparse

def parse():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c", "--cron",
        help="run in cron mode instead of web app mode",
        action="store_true",
    )
    parser.add_argument(
        "-b", "--build",
        help="accept software build requests",
        action="store_true",
    )
    parser.add_argument(
        "-t", "--test",
        help="accept software test requests",
        action="store_true",
    )

    parser.add_argument(
        "-f", "--file",
        help="use event data from a JSON file",
    )

    parser.add_argument(
        "-p", "--port", default=3000,
        help="listen on a specific port for events (default 3000)",
    )
    return parser.parse_args()
