import logging
import optparse
import os
import sys

from osci.config import Configuration
import pyrax.exceptions
import pyrax

def get_parser():
    usage = "usage: %prog [options] <source directory> <target path>"

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      default=False, help='enable verbose (debug) logging')
    parser.add_option('-c', '--container', dest='container',
                      help='Container to upload to.  Defaults to config file setting.')

    return parser

def get_content_encoding(filename):
    if filename.endswith('.gz'):
        return 'gzip'
    return None

def get_content_type(filename):
    split_fn = filename.split('.')
    if split_fn[-1] in ['gz']:
        split_fn = split_fn[:-1]
    if split_fn[-1] in ['txt', 'log', 'conf', 'sh']:
        return 'text/plain'
    if split_fn[0] in ['messages']:
        return 'text/plain'
    if split_fn[-1] in ['html']:
        return 'text/html'
    return None

_START_STANSA = """
<html>
 <head>
  <title>Test results for %(prefix)s</title>
 </head>
 <body>
  <h1>Test results for %(prefix)s</ht>
  <table>
  <tr><th>Name</th><th>Size</th></tr>
"""
_FILE_STANSA = """
  <tr><td><a href="%(filename)s">%(filename)s</a></td><td>%(size)s</td></tr>
"""
_END_STANSA = """  </table>
 </body>
</html>
"""
def _html_start_stansa(prefix):
    return _START_STANSA % locals()

def _html_file_stansa(filename, size):
    return _FILE_STANSA % locals()

def _html_end_stansa():
    return _END_STANSA % locals()

class UploadException(Exception):
    pass

class SwiftUploader(object):
    logger = logging.getLogger('citrix.swiftupload')

    def upload_one_file(self, container, source, target, attempt=0):
        self.logger.info('Uploading %s to %s', source, target)
        chksum = pyrax.utils.get_checksum(source)
        content_encoding=get_content_encoding(source)
        content_type=get_content_type(source)

        obj = container.upload_file(source, target,
                                    content_encoding=content_encoding,
                                    content_type=content_type, etag=chksum)
        if chksum != obj.etag:
            if attempt < Configuration().get_int('SWIFT_UPLOAD_ATTEMPTS'):
                self.logger.error('Upload of %s to %s failed - retrying'%(source, target))
                self.upload_one_file(container, source, target, attempt+1)
            else:
                raise UploadException('Failed to upload %s'%source)

    def upload_dir(self, local_dir, local_prefix, cf_prefix, container):
        contents = ""
        filenames = os.listdir(os.path.join(local_dir, local_prefix))
        filenames.sort()
        if 'run_tests.log' in filenames:
            filenames.remove('run_tests.log')
            filenames.insert(0, 'run_tests.log')
        for filename in filenames:
            full_path = os.path.join(local_dir, local_prefix, filename)

            if os.path.isdir(full_path):
                contents = contents + self.upload_dir(local_dir,
                                                      os.path.join(local_prefix, filename),
                                                      cf_prefix,
                                                      container)
            else:
                stats = os.stat(full_path)
                contents = contents + _html_file_stansa(os.path.join(local_prefix, filename), stats.st_size)

                cf_name = os.path.join(cf_prefix, local_prefix, filename)
                self.upload_one_file(container, full_path, cf_name)
        return contents

    def upload(self, local_dir, cf_prefix, container_name=None):
        pyrax.set_setting('identity_type', 'rackspace')
        try:
            pyrax.set_credentials(Configuration().SWIFT_USERNAME,
                                  Configuration().SWIFT_API_KEY,
                                  region=Configuration().SWIFT_REGION)
        except pyrax.exceptions.AuthenticationFailed, e:
            self.logger.exception(e)
            raise
        cf = pyrax.cloudfiles

        if not container_name:
            container_name = Configuration().SWIFT_CONTAINER
        container = cf.create_container(container_name)

        contents = _html_start_stansa(cf_prefix)

        contents = contents + self.upload_dir(local_dir, '', cf_prefix, container)

        contents = contents + _html_end_stansa()
        container.store_object('%s/results.html'%cf_prefix, contents)

        uri = container.cdn_uri
        result_url = "%s/%s/results.html"%(uri, cf_prefix)
        self.logger.info('Result URL: %s', result_url)
        return result_url


def main():
    parser = get_parser()
    (options, args) = parser.parse_args()

    level = logging.DEBUG if options.verbose else logging.INFO
    logging.basicConfig(
        format=u'%(asctime)s %(levelname)s %(name)s %(message)s',
        level=level)

    for logger_name in ['paramiko.transport', 'paramiko.transport.sftp',
                        'requests.packages.urllib3.connectionpool']:
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    local_dir = args[0]
    cf_prefix = args[1]

    SwiftUploader().upload(local_dir, cf_prefix, options.container)


if __name__ == "__main__":
    sys.exit(main())
