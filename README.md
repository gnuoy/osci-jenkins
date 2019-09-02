# OSCI Jenkins Report

Run a report on jobs that have run in osci in the past X hours.

```
usage: jenkins-report.py [-h] [-j JOB_NAME] [-t HOURS_AGO] [-s]

optional arguments:
  -h, --help            show this help message and exit
  -j JOB_NAME, --job-name JOB_NAME
                        Name of job e.g. mojo_runner, test_charm_lint etc
  -t HOURS_AGO, --hours-ago HOURS_AGO
                        Time period to report on. (HOURS_AGO < time < now)
  -s, --include-success
                        Whether to include successful runs
```

Run directly through tox:

```
$ tox -e jenkins-report -- -t 48 -j mojo  -s
```

Create venv and run within it:

```
$ tox -e venv
$ source .tox/venv/bin/activate
(venv) $ ./jenkins-report.py -t 48 -j mojo  -s
```
