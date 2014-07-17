import paramiko
import logging
import socket
import os
import fnmatch
from stat import S_ISREG
import subprocess
import errno
import json

from osci.config import Configuration
from osci.executor import RealExecutor
from osci import localhost
from osci import node


Executor = RealExecutor


def mkdir_recursive(target, target_dir):
    try:
        target.chdir(target_dir)
    except:
        mkdir_recursive(target, os.path.dirname(target_dir))
        target.mkdir(target_dir)

def copy_logs(source_masks, target_dir, host, username, key_filename, upload=True):
    ssh = getSSHObject(host, username, key_filename)
    sftp = ssh.open_sftp()
    try:
        copy_logs_sftp(sftp, source_masks, target_dir, host, username, key_filename, upload)
    finally:
        sftp.close()
        ssh.close()

def copy_logs_sftp(sftp, source_masks, target_dir, host, username, key_filename, upload):
    logger = logging.getLogger('citrix.copy_logs')
    if upload:
        source = os
        target = sftp
        sftp_method = sftp.put
    else:
        source = sftp
        target = os
        sftp_method = sftp.get

    mkdir_recursive(target, target_dir)

    existing_files = target.listdir(target_dir)
    for filename in existing_files:
        target.remove(os.path.join(target_dir, filename))

    for source_mask in source_masks:
        try:
            source_dir = os.path.dirname(source_mask)
            source_glob = os.path.basename(source_mask)
            for filename in source.listdir(source_dir):
                if not fnmatch.fnmatch(filename, source_glob):
                    continue
                source_file = os.path.join(source_dir, filename)
                if S_ISREG(source.stat(source_file).st_mode):
                    logger.info('Copying %s to %s', source_file, target_dir)
                    try:
                        sftp_method(os.path.join(source_dir, filename),
                                    os.path.join(target_dir, filename))
                    except IOError, e:
                        logger.exception(e)
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
            logger.exception(e)
            # Ignore this exception to try again on the next directory

def execute_command(command, delimiter=' ', silent=False, return_streams=False):
    command_as_array = command.split(delimiter)
    if not silent:
        logging.debug("Executing command: %s", command_as_array)
    p = subprocess.Popen(command_as_array, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = p.communicate()
    if p.returncode != 0:
        if not silent:
            logging.error("Error: Could not execute command. "+\
                          "Failed with code %d and errors: %s",
                          p.returncode, errors)
    if not silent:
        logging.debug("Output:%s", output)

    if return_streams:
        return p.returncode, output, errors
    return p.returncode == 0

def testSSH(ip, username, key_filename):
    return execute_command('ssh -q -o BatchMode=yes -o UserKnownHostsFile=/dev/null '+\
                                 '-o StrictHostKeyChecking=no -i %s %s@%s /bin/true'%(
                                     key_filename, username, ip))

def getSSHObject(ip, username, key_filename):
    if ip is None:
        raise Exception('Seriously?  The host must have an IP address')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
    key = paramiko.RSAKey.from_private_key_file(key_filename)
    ssh.connect(ip, username=username, pkey=key)
    return ssh

def vote(commitid, vote_num, message):
    #ssh -p 29418 review.example.com gerrit review -m '"Test failed on MegaTestSystem <http://megatestsystem.org/tests/1234>"'
    # --verified=-1 c0ff33
    logging.info("Going to vote commitid %s, vote %s, message %s",
                 commitid, vote_num, message)
    if not Configuration().get_bool('VOTE_NEGATIVE') and vote_num == "-1":
        logging.error("Did not vote -1 for commitid %s, vote %s",
                      commitid, vote_num)
        vote_num = "0"
        message += "\n\nNegative vote suppressed"
    vote_cmd = "ssh$-q$-o$BatchMode=yes$-o$UserKnownHostsFile=/dev/null$-o$StrictHostKeyChecking=no$-p$%s$%s@%s$gerrit$review"%(Configuration().GERRIT_PORT, Configuration().GERRIT_USERNAME, Configuration().GERRIT_HOST)
    vote_cmd = vote_cmd + "$-m$'" + message + "'"
    if Configuration().get_bool('VOTE_SERVICE_ACCOUNT'):
        vote_cmd = vote_cmd + "$--verified=" + vote_num
    vote_cmd = vote_cmd + "$" + commitid
    is_executed = execute_command(vote_cmd, '$')
    if not is_executed:
        logging.error("Error: Could not vote. Voting failed for change %s ", commitid)
    else:
        logging.info("Successfully voted %s for change %s", vote_num, commitid)

def get_commit_json(change_id):
    # ssh -i ~/.ssh/citrix_gerrit -p 29418 citrix_xenserver_ci@10.80.2.68 gerrit query --format=JSON limit:2 73641 --patch-sets
    query = "ssh$-q$-o$BatchMode=yes$-o$UserKnownHostsFile=/dev/null$-o$StrictHostKeyChecking=no"
    query = query + "$-p$%s$%s@%s$gerrit$query"%(Configuration().GERRIT_PORT,
                                                Configuration().GERRIT_USERNAME,
                                                Configuration().GERRIT_HOST)
    query = query + "$--format=JSON$limit:1$--patch-sets"
    query = query + "$" + change_id
    (code, stdout, stderr) = execute_command(query, '$', return_streams=True)
    if code == 0:
        return json.loads(stdout.splitlines()[0])

def get_patchset_details(change_id, patchset_id):
    commit_json = get_commit_json(change_id)
    patch_sets = commit_json['patchSets']
    matching_patches = [i for i in patch_sets if i['number'] == patchset_id]
    matching_patch = matching_patches[0]
    matching_patch['project'] = commit_json['project']
    return matching_patches[0]


def copy_dom0_logs(host, user, keyfile, local_directory):
    dom0_files = (
        '/var/log/messages* /var/log/SMlog* /var/log/xensource* /opt/nodepool-scripts/*.log'
    )

    xecutor = Executor()
    test_node = node.Node(
        dict(node_username=user, node_host=host, node_keyfile=keyfile))
    this_host = localhost.Localhost()

    xecutor.pipe_run(
        test_node.command_to_get_dom0_files_as_tgz_to_stdout(dom0_files),
        this_host.commands_to_extract_stdout_tgz_to(local_directory)
    )

