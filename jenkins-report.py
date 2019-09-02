#!/usr/bin/env python3

# Copyright 2019 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import datetime
import functools
import os
import re
import sys
import jenkins
import texttable
import yaml

JENKINS_SETTINGS_FILE = "{home}/.jenkins.yaml"

job_aliases = {
    'mojo': 'mojo_runner',
    'full': 'test_charm_func_full',
    'lint': 'test_charm_lint',
    'single': 'test_charm_single'}

server = None


def search_for_cause(job_name, number):
    """Match a build failure with a cause by examining build console output.

    :param job_name: Name of job to search for.
    :type job_name: str
    :param number: The build number of the job.
    :type number: int
    :returns: A list of cause keys.
    :rtype: []
    """
    failure_reasons = []
    output = get_server().get_build_console_output(job_name, number)
    causes = get_causes()
    for cause_name, cause_data in causes.items():
        if cause_data.get('re'):
            for reg_exp in cause_data.get('re'):
                if re.search(reg_exp, output, re.DOTALL):
                    failure_reasons.append(cause_name)
        if cause_data.get('text'):
            for search_str in cause_data.get('text'):
                if search_str in output:
                    failure_reasons.append(cause_name)
    return list(set(failure_reasons))


@functools.lru_cache(maxsize=200)
def get_causes():
    """Load the causes from a file and return the cause dict.

    If this function has been called before then the cached results are
    returned.

    :returns: A dict of cause information.
    :rtype: {}
    """
    causes_file = "causes.yaml"
    with open(causes_file, 'r') as f:
        data = yaml.safe_load(f)
    return data


def get_connection_settings():
    """Return connection settings from a file and return them.

    :returns: A dict of connection information.
    :rtype: {}
    """
    config_file = JENKINS_SETTINGS_FILE.format(home=os.environ['HOME'])
    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print("Jenkins config file not found")
        print("Please create {}".format(config_file))
        print("\nExample Contents:")
        print("username: <username>")
        print("password: <password>")
        print("url: http://10.245.162.58:8080")
        sys.exit(1)
    return data


def get_server():
    """Return connection settings from a file and return them.

    :returns: A jenkins connection object.
    :rtype: jenkins.Jenkins
    """
    global server
    if not server:
        connection_settings = get_connection_settings()
        server = jenkins.Jenkins(
            connection_settings['url'],
            username=connection_settings['username'],
            password=connection_settings['password'])
    return server


def get_jobs():
    """Return a list of all jenkins jobs

    :returns: A list of jenkins jobs
    :rtype: []
    """
    return get_server().get_jobs()


def display_build_summary(build_statuses):
    """Display a table of results from the given builds.

    :param build_statuses: Dict of build_statuses
    :type build_statuses: {'build id':
                              'job_name': job_name,
                              'build_info': build_info,
                              'build_number': build_number,
                              'cause_info': cause_info}
    """
    causes = get_causes()
    table = texttable.Texttable()
    table.set_max_width(0)
    rows = [[
        "Job Name",
        "Build No.",
        "Status",
        "Cause",
        "Bug URL(s)",
        "Build URL",
        "Build Info"]]
    for build_data in build_statuses.values():
        bug_urls = [causes[c].get('bug_data', {}).get('url', '')
                    for c in build_data['cause_info']]
        rows.append([
            build_data['job_name'],
            build_data['build_number'],
            build_data['build_info']['result'],
            '\n'.join(build_data['cause_info']),
            '\n'.join(bug_urls),
            build_data['build_info']['url'],
            build_data['build_info'].get('displayName', '')])
    table.add_rows(rows)
    print(table.draw())


def get_build_info(job_name, build_number):
    """Return a dict of build info for the given build

    Retrieve build info from jenkins and tidy it up. For example make the
    timestamp useful.

    :param job_name: Name of job to search for.
    :type job_name: str
    :param build_number: The build number of the job.
    :type build_number: int
    :returns: Dict of build info
    :rtype: {}
    """
    build_info = get_server().get_build_info(job_name, build_number)
    build_info['timestamp'] = datetime.datetime.fromtimestamp(
        build_info['timestamp']/1000)
    return build_info


def is_build_included(build_info, min_start_time, include_success):
    """Check if the build should be included in the report.

    :param build_info: Dict of information about the build
    :type build_info: {}
    :param min_start_time: Oldest build time.
    :type min_start_time: datetime.datetime
    :param include_success: Whether to include successful builds in the report
    :type include_success: bool
    :returns: Whether build should be included.
    :rtype: bool
    """
    include_build = True
    if build_info['timestamp'] < min_start_time:
        include_build = False
    elif build_info['result'] == 'SUCCESS' and not include_success:
        include_build = False
    return include_build


def get_build_fail_cause(build_info, job_name, build_number):
    """Try and match failure against a known cause.

    :param build_info: Dict of information about the build
    :type build_info: {}
    :param job_name: Name of job to search for.
    :type job_name: str
    :param build_number: The build number of the job.
    :type build_number: int
    :returns: Dict of cause info
    :rtype: {}
    """
    if build_info['result'] == 'SUCCESS':
        cause_info = ''
    else:
        cause_info = search_for_cause(job_name, build_number)
    return cause_info


def display_builds_for_job(job_name, hours_ago=24, include_success=True):
    """Check all build in the given timeslot and report on their status

    :param job_name: Name of job to search for.
    :type job_name: str
    :param hours_ago: Numbers before now to search for jobs in.
    :type hours_ago: int
    :param include_success: Whether to include succesful run in report.
    :type include_success: bool
    """
    now = datetime.datetime.now()
    min_start_time = now - datetime.timedelta(hours=hours_ago)
    last_build = get_server().get_job_info(job_name)['lastCompletedBuild']
    if not last_build:
        return
    build_number = last_build['number']
    build_statuses = {}
    job_time = now
    while job_time > min_start_time:
        build_info = get_build_info(job_name, build_number)
        job_time = build_info['timestamp']
        if is_build_included(build_info, min_start_time, include_success):
            cause_info = get_build_fail_cause(
                build_info,
                job_name,
                build_number)
            build_statuses['{}_{}'.format(job_name, build_number)] = {
                'job_name': job_name,
                'build_info': build_info,
                'build_number': build_number,
                'cause_info': cause_info}
        build_number = build_number - 1
    display_build_summary(build_statuses)


def parse_args():
    """Parse command line arguments

    :returns: Dict of run settings
    :rtype: {}
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-j",
        "--job-name",
        help="Name of job e.g. mojo_runner, test_charm_lint etc")
    parser.add_argument(
        "-t",
        "--hours-ago",
        help="Time period to report on. (HOURS_AGO < time < now)")
    parser.add_argument(
        "-s",
        "--include-success",
        help="Whether to include successful runs",
        default=False,
        action='store_true')
    args = parser.parse_args()
    job_name = args.job_name or 'mojo_runner'
    hours_ago = args.hours_ago or 30
    hours_ago = int(hours_ago)
    job_name = job_aliases.get(job_name) or job_name
    return {
        'job_name': job_name,
        'hours_ago': hours_ago,
        'include_success': args.include_success}


if __name__ == '__main__':
    run_settings = parse_args()
    display_builds_for_job(
        run_settings['job_name'],
        hours_ago=run_settings['hours_ago'],
        include_success=run_settings['include_success'])
