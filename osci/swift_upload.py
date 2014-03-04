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

    return parser

def get_content_encoding(filename):
    if filename.endswith('.gz'):
        return 'gzip'
    return None

def _html_start_stansa(prefix):
    return """
<html>
 <head>
  <title>Test results for %(prefix)s</title>
 </head>
 <body>
  <h1>Test results for %(prefix)s</ht>
  <table>
  <tr><th>Name</th><th>Size</th></tr>
""" % locals()

def _html_file_stansa(filename, size):
    return """
  <tr><td><a href="%(filename)s">%(filename)s</td><td>%(size)s</td></tr>
""" % locals()

def _html_end_stansa():
    return """  </table>
 </body>
</html>
""" % locals()

class UploadException(Exception):
    pass

class SwiftUploader(object):
    logger = logging.getLogger('citrix.swiftupload')
    
    def upload_one_file(self, container, source, target, attempt=0):
        self.logger.info('Uploading %s to %s', source, target)
        chksum = pyrax.utils.get_checksum(source)
        content_encoding=get_content_encoding(source)
        obj = container.upload_file(source, target, content_encoding=content_encoding, etag=chksum)
        if chksum != obj.etag:
            if attempt < Configuration().get_int('SWIFT_UPLOAD_ATTEMPTS'):
                self.logger.error('Upload of %s to %s failed - retrying'%(source, target))
                self.upload_one_file(container, source, target, attempt+1)
            else:
                raise UploadException('Failed to upload %s'%source)
    
    def upload(self, local_dir, cf_prefix):
        pyrax.set_setting('identity_type', 'rackspace')
        try: 
            pyrax.set_credentials(Configuration().SWIFT_USERNAME, Configuration().SWIFT_API_KEY)
        except pyrax.exceptions.AuthenticationFailed, e:
            self.logger.exception(e)
            raise
        cf = pyrax.cloudfiles
        
        container = cf.create_container(Configuration().SWIFT_CONTAINER)
        
        contents = _html_start_stansa(cf_prefix)
        for filename in os.listdir(local_dir):
            full_path = os.path.join(local_dir, filename)
            
            stats = os.stat(full_path)
            contents = contents + _html_file_stansa(filename, stats.st_size)
            
            cf_name = "%s/%s"%(cf_prefix, filename)
            self.upload_one_file(container, full_path, cf_name)
                                 
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

    SwiftUploader().upload(local_dir, cf_prefix)


if __name__ == "__main__":
    sys.exit(main())
