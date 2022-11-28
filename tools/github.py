# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Bob Droege (@bedroge)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#
import re


def get_comment(pr, job_id):
    comments = pr.get_issue_comments()
    for comment in comments:
        # NOTE adjust search string if format changed by event
        #        handler (separate process running
        #        eessi_bot_event_handler.py)
        cms = f".*submitted.*job id `{job_id}`.*"

        comment_match = re.search(cms, comment.body)

        if comment_match:
            return comment
        return None


def update_comment(cmnt_id, pr, update):
    issue_comment = pr.get_issue_comment(int(cmnt_id))
    original_body = issue_comment.body
    issue_comment.edit(original_body + update)
