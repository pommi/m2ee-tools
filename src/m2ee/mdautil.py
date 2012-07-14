#
# Copyright (c) 2009-2012, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import os
import shutil
import subprocess
from log import logger

class M2EEMdaUtil:

    def __init__(self, config):
        self._config = config

    def unpack(self, mda_name):
        
        mda_file_name = os.path.join(self._config.get_model_upload_path(), mda_name)
        if not os.path.isfile(mda_file_name):
            logger.error("file %s does not exist" % mda_file_name)
            return False

        logger.debug("Testing archive...")
        cmd = ("unzip", "-tqq", mda_file_name)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout,stderr) = proc.communicate()

        if proc.returncode != 0:
            logger.error("An error occured while testing archive consistency: ")
            if stdout != '':
                logger.error(stdout)
            if stderr != '':
                logger.error(stderr)
            return False

        logger.info("This command will replace the contents of the model/ and web/ locations, using the files extracted from the archive")
        answer = raw_input("Continue? (y)es, (n)o? ")
        if answer != 'y':
            logger.info("Aborting!")
            return False

        logger.debug("Removing everything in model/ and web/ locations...")
        # TODO: error handling. removing model/ and web/ itself should not be possible (parent dir is root owned), all errors ignored for now
        shutil.rmtree(os.path.join(self._config.get_app_base(), 'model'), ignore_errors=True)
        shutil.rmtree(os.path.join(self._config.get_app_base(), 'web'), ignore_errors=True)

        logger.debug("Extracting archive...")
        cmd = ("unzip", "-oq", mda_file_name, "web/*", "model/*", "-d", self._config.get_app_base())
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout,stderr) = proc.communicate()

        if proc.returncode != 0:
            logger.error("An error occured while extracting archive: ")
            if stdout != '':
                print logger.error(stdout)
            if stderr != '':
                print logger.error(stderr)
            return False

        # XXX: reset permissions on web/ model/ to be sure after executing this function
        return True

    def complete_unpack(self, text):
        model_upload_path = self._config.get_model_upload_path()
        return [f for f in os.listdir(model_upload_path)
                if os.path.isfile(os.path.join(model_upload_path, f))
                and f.startswith(text)
                and (f.endswith(".zip") or f.endswith(".mda"))]
