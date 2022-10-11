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

    parser.add_argument(
        "-i", "--max-manager-iterations", default=-1,
        help="loop behaviour: i<0 - indefinite, i==0 - don't run, i>0: run i iterations (default -1)",
    )

    parser.add_argument(
        "-j", "--jobs",
        help="limits the processing to a specific job id or list of comma-separated list of job ids",
    )

    parser.add_argument(
        "-o", "--original-job-dir",
        help="original job directory when resubmitting",
    )

    parser.add_argument(
        "-m", "--modified-job-dir",
        help="directory containing modifications to the original job",
    )

    parser.add_argument(
        "-n", "--pr-number",
        help="number of the pull request",
    )

    parser.add_argument(
        "-r", "--repository-name",
        help="name of the repository including username, e.g, USER/repository",
    )

    return parser.parse_args()
