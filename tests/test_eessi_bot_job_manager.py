# Tests for 'job manager' task of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jonas Qvigstad (@jonas-lq)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

from eessi_bot_job_manager import EESSIBotSoftwareLayerJobManager


def test_determine_running_jobs():
    job_manager = EESSIBotSoftwareLayerJobManager()

    assert job_manager.determine_running_jobs({}) == []

    current_jobs_all_pending = {
        '0': {
            'jobid': '0',
            'state': 'PENDING',
            'reason': 'c11-59'
        },
        '1': {
            'jobid': '1',
            'state': 'PENDING',
            'reason': 'c5-57'
        },
        '2': {
            'jobid': '2',
            'state': 'PENDING',
            'reason': 'c5-56'
        }
    }
    assert job_manager.determine_running_jobs(current_jobs_all_pending) == []

    current_jobs_some_running = {
        '0': {
            'jobid': '0',
            'state': 'RUNNING',
            'reason': 'c11-59'
        },
        '1': {
            'jobid': '1',
            'state': 'PENDING',
            'reason': 'c5-57'
        },
        '2': {
            'jobid': '2',
            'state': 'RUNNING',
            'reason': 'c5-56'
        }
    }
    assert job_manager.determine_running_jobs(current_jobs_some_running) == ["0", "2"]


def test_determine_new_jobs():
    job_manager = EESSIBotSoftwareLayerJobManager()

    current_jobs = {
        '0': {
            'jobid': '0', 'state': '', 'reason': ''
        },
        '1': {
            'jobid': '1', 'state': '', 'reason': ''
        },
        '2': {
            'jobid': '2', 'state': '', 'reason': ''
        }
    }
    known_jobs_one_job = {
        '0': {
            'jobid': '0'
        }
    }
    known_jobs_all_jobs = {
        '0': {
            'jobid': '0'
        },
        '1': {
            'jobid': '1'
        },
        '2': {
            'jobid': '2'
        }
    }

    assert job_manager.determine_new_jobs({}, current_jobs) == ['0', '1', '2']
    assert job_manager.determine_new_jobs(known_jobs_one_job, current_jobs) == ['1', '2']
    assert job_manager.determine_new_jobs(known_jobs_all_jobs, current_jobs) == []


def test_determine_finished_jobs():
    job_manager = EESSIBotSoftwareLayerJobManager()

    current_jobs_all_jobs = {
        '0': {
            'jobid': '0', 'state': '', 'reason': ''
        },
        '1': {
            'jobid': '1', 'state': '', 'reason': ''
        },
        '2': {
            'jobid': '2', 'state': '', 'reason': ''
        }
    }
    current_jobs_one_job = {
        '0': {
            'jobid': '0', 'state': '', 'reason': ''
        }
    }

    known_jobs = {
        '0': {
            'jobid': '0'
        },
        '1': {
            'jobid': '1'
        },
        '2': {
            'jobid': '2'
        }
    }

    assert job_manager.determine_finished_jobs(known_jobs, current_jobs_all_jobs) == []
    assert job_manager.determine_finished_jobs(known_jobs, current_jobs_one_job) == ['1', '2']
    assert job_manager.determine_finished_jobs(known_jobs, {}) == ['0', '1', '2']


def test_parse_scontrol_show_job_output():
    # Dummy output (shortened) from Slurm 25.11.3 for "scontrol show job <jobid>"
    scontrol_output = 'JobId=123 JobName=bot_test_job UserId=eessibot(12345) MCS_label=N/A EligibleTime=Unknown' \
                      ' AllocNode:Sid=my.node.name:123456 SubmitLine=/opt/slurm/25.11.3/bin/sbatch --hold' \
                      ' --time=10-0:0:0 --nodes=1 --exclusive --cpus-per-task=1 --job-name=bot_test_job ' \
                      '/home/eessibot/job.slurm WorkDir=/jobs/2026.01/pr_123/event_123-456-789/run_000/riscv64/' \
                      'generic/dev.eessi.io-riscv StdErr= StdIn=/dev/null StdOut=/jobs/2026.01/pr_123/' \
                      'event_123-456-789/run_000/riscv64/generic/dev.eessi.io-riscv/slurm-123.out TresPerTask=cpu=1'
    job_manager = EESSIBotSoftwareLayerJobManager()
    job_info = job_manager.parse_scontrol_show_job_output(scontrol_output)
    job_info_expected = {
        'JobId': '123',
        'JobName': 'bot_test_job',
        'UserId': 'eessibot(12345)',
        'MCS_label': 'N/A',
        'EligibleTime': 'Unknown',
        'AllocNode:Sid': 'my.node.name:123456',
        'SubmitLine': '/opt/slurm/25.11.3/bin/sbatch --hold --time=10-0:0:0 --nodes=1 --exclusive --cpus-per-task=1 '
                      '--job-name=bot_test_job /home/eessibot/job.slurm',
        'WorkDir': '/jobs/2026.01/pr_123/event_123-456-789/run_000/riscv64/generic/dev.eessi.io-riscv',
        'StdErr': '',
        'StdIn': '/dev/null',
        'StdOut': '/jobs/2026.01/pr_123/event_123-456-789/run_000/riscv64/generic/dev.eessi.io-riscv/slurm-123.out',
        'TresPerTask': 'cpu=1',
    }
    assert job_info == job_info_expected
