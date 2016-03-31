#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of Kubespray.
#
#    Foobar is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Foobar is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Foobar.  If not, see <http://www.gnu.org/licenses/>.

"""
kubespray.deploy
~~~~~~~~~~~~

Deploy a kubernetes cluster. Run the ansible-playbbook
"""

import sys
import os
import re
import signal
from subprocess import PIPE, STDOUT, Popen, check_output, CalledProcessError
from kubespray.common import get_logger, query_yes_no, run_command
from ansible.utils.display import Display
display = Display()


class RunPlaybook(object):
    '''
    Run the Ansible playbook to deploy the kubernetes cluster
    '''
    def __init__(self, options):
        self.options = options
        self.inventorycfg = os.path.join(
            options['kubespray_path'],
            'inventory/inventory.cfg'
        )
        self.logger = get_logger(
            options.get('logfile'),
            options.get('loglevel')
        )
        self.logger.debug(
            'Running ansible-playbook command with the following options: %s'
            % self.options
        )

    def ssh_prepare(self):
        '''
        Run ssh-agent and store identities
        '''
        try:
            sshagent = check_output('ssh-agent')
        except CalledProcessError as e:
            display.error('Cannot run the ssh-agent : %s' % e.output)
        # Set environment variables
        ssh_envars = re.findall('\w*=[\w*-\/.*]*', sshagent)
        for v in ssh_envars:
            os.environ[v.split('=')[0]] = v.split('=')[1]
        # Store ssh identity
        try:
            proc = Popen(
                'ssh-add', stdout=PIPE, stderr=STDOUT, stdin=PIPE, shell=True
            )
            proc.stdin.write('password\n')
            proc.stdin.flush()
            response_stdout, response_stderr = proc.communicate()
            display.display(response_stdout)
        except CalledProcessError as e:
            display.error('Failed to store ssh identity : %s' % e.output)
        if response_stderr:
            display.error(response_stderr)
            self.logger.critical(
                'Deployment stopped because of ssh credentials'
                % self.filename
            )
            os.kill(int(os.environ.get('SSH_AGENT_PID')), signal.SIGTERM)
            sys.exit(1)

    def check_ping(self):
        '''
         Check if hosts are reachable
        '''
        display.banner('CHECKING SSH CONNECTIONS')
        cmd = [
            os.path.join(self.options['ansible_path'], 'ansible'),
            '--ssh-extra-args', '-o StrictHostKeyChecking=no', '-u',
            '%s' % self.options['ansible_user'],
            '-b', '--become-user=root', '-m', 'ping', 'all',
            '-i', self.inventorycfg
        ]
        rcode, emsg = run_command('SSH ping hosts', cmd)
        if rcode != 0:
            self.logger.critical('Cannot connect to hosts: %s' % emsg)
            os.kill(int(os.environ.get('SSH_AGENT_PID')), signal.SIGTERM)
            sys.exit(1)
        display.display('All hosts are reachable', color='green')

    def deploy_kubernetes(self):
        '''
        Run the ansible playbook command
        '''
        cmd = [
            os.path.join(self.options['ansible_path'], 'ansible-playbook'),
            '--ssh-extra-args', '-o StrictHostKeyChecking=no',
            '-e', 'kube_network_plugin=%s' % self.options['network_plugin'],
            '-u',  '%s' % self.options['ansible_user'],
            '-b', '--become-user=root', '-i', self.inventorycfg,
            os.path.join(self.options['kubespray_path'], 'cluster.yml')
        ]
        if 'ansible_opts' in self.options.keys():
            cmd = cmd + self.options['ansible_opts'].split(' ')
        for cloud in ['aws', 'gce']:
            if self.options[cloud]:
                cmd = cmd + ['-e', 'cloud_provider=%s' % cloud]
        display.display(' '.join(cmd), color='bright blue')
        if self.options['interactive']:
            query_yes_no(
                'Run kubernetes cluster deployment with the above command ?'
            )
        display.banner('RUN PLAYBOOK')
        self.logger.info(
            'Running kubernetes deployment with the command: %s' % cmd
        )
        rcode, emsg = run_command('Run deployment', cmd)
        if rcode != 0:
            self.logger.critical('Deployment failed: %s' % emsg)
            os.kill(int(os.environ.get('SSH_AGENT_PID')), signal.SIGTERM)
            sys.exit(1)
        display.display('Kubernetes deployed successfuly', color='green')
        os.kill(int(os.environ.get('SSH_AGENT_PID')), signal.SIGTERM)
