#!/usr/bin/python
import os
import m2ee
import subprocess
from flask import Flask, request, jsonify
from werkzeug import secure_filename

class REST():

    def __init__(self, app, yaml_files=None):
        self.app = app
        self.m2ee = m2ee.M2EE()
        self.upload_folder = os.path.expanduser('~/data/model-upload')

    def run(self):
        if not os.path.exists(os.path.expanduser('~/.nginx.pid')):
            subprocess.call(["/usr/sbin/nginx", "-c", os.path.expanduser('~/nginx.conf')])

        self.app.add_url_rule("/", 'index', self.index)
        self.app.add_url_rule("/about/", 'about', self.about)
        self.app.add_url_rule("/status/", 'status', self.status)
        self.app.add_url_rule("/stop/", 'stop', self.stop, methods=['POST'])
        self.app.add_url_rule("/terminate/", 'terminate', self.terminate, methods=['POST'])
        self.app.add_url_rule("/kill/", 'kill', self.kill, methods=['POST'])
        self.app.add_url_rule("/start/", 'start', self.start, methods=['POST'])
        self.app.add_url_rule("/upload/", 'upload', self.upload, methods=['POST'])
        self.app.add_url_rule("/unpack/", 'unpack', self.unpack, methods=['POST'])
        self.app.add_url_rule("/emptydb/", 'emptydb', self.emptydb, methods=['POST'])
        self.app.add_url_rule("/config/", 'config', self.config, methods=['GET', 'POST'])
        self.app.debug = True
        self.app.run(host='0.0.0.0')

    def say(self, string):
        if isinstance(string, str):
            string = [string]
        return "\n".join(string) + "\n"

    def index(self):
        return self.say("Mendix REST API v0.1")

    def about(self):
        output = []
        output.append('Using m2ee-tools version %s' % m2ee.__version__)
        if self._report_not_running():
            return self.say(output)
        feedback = self.m2ee.client.about().get_feedback()
        output.append("Using %s version %s" % (feedback['name'], feedback['version']))
        output.append(feedback['copyright'])
        if self.m2ee.config.get_runtime_version() // 2.5:
            if 'company' in feedback:
                output.append('Project company name is %s' % feedback['company'])
            if 'partner' in feedback:
                output.append('Project partner name is %s' % feedback['partner'])
        if self.m2ee.config.get_runtime_version() >= 4.4:
            if 'model_version' in feedback:
                output.append('Model version: %s' % feedback['model_version'])
        return self.say(output)

    def status(self):
        output = []
        if self._report_not_running():
            return self.say("The application process is not running.")
        feedback = self.m2ee.client.runtime_status().get_feedback()
        output.append("The application process is running, the MxRuntime has "
                    "status: %s" % feedback['status'])
        return self.say(output)

    def stop(self):
        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if not pid_alive and not m2ee_alive:
            return self.say("Nothing to stop, the application is not running.")

        if self.m2ee.stop():
            return self.say("App stopped.")
        return self.say("Couldn't stop app.")

    def terminate(self):
        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if not pid_alive and not m2ee_alive:
            return self.say("Nothing to terminate, the application is not running.")

        if self.m2ee.terminate():
            return self.say("App terminated.")
        return self.say("Couldn't terminate app.")

    def kill(self):
        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if not pid_alive and not m2ee_alive:
            return self.say("Nothing to kill, the application is not running.")

        if self.m2ee.kill():
            return self.say("App killed.")
        return self.say("Couldn't kill app.")

    def start(self):
        """
        This function deals with the start-up sequence of the Mendix Runtime.
        Starting the Mendix Runtime can fail in both a temporary or permanent
        way. See the client_errno for possible error codes.
        """
        if not self.m2ee.start_appcontainer():
            return self.say("start_appcontainer failed")

        if not self.m2ee.send_runtime_config():
            self.stop()
            return self.say("send_runtime_config failed")

        startresponse = self.m2ee.start_runtime({})

        result = startresponse.get_result()
        if result == m2ee.client_errno.start_INVALID_DB_STRUCTURE:
            feedback = self.m2ee.client.get_ddl_commands({"verbose": True}).get_feedback()
            ddl_commands = feedback['ddl_commands']
            self.m2ee.save_ddl_commands(ddl_commands)
            m2eeresponse = self.m2ee.client.execute_ddl_commands()

            self.m2ee.start_runtime({})
            return self.say("App started. (Database updated)")

        return self.say("App started.")

    def _report_not_running(self):
        """
        To be used by actions to see whether m2ee is available for executing
        requests. Also prints a line when the application is not running.

        if self._report_not_running():
            return
        do_things_that_communicate_using_m2ee_client()

        returns True when m2ee is not available for requests, else False
        """
        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if not pid_alive and not m2ee_alive:
            self.say("The application process is not running.")
            return True
        # if pid is alive, but m2ee does not respond, errors are already
        # printed by check_alive
        if pid_alive and not m2ee_alive:
            return True
        return False

    def upload(self):
        file = request.files['model']
        file.save(os.path.join(self.upload_folder, 'model.mda'))
        return self.say('File uploaded.')

    def unpack(self):
        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if pid_alive or m2ee_alive:
            return self.say("The app is still running, refusing to unpack.")

        self.m2ee.unpack('model.mda')

        mxversion = self.m2ee.config.get_runtime_version()
        version = str(mxversion)
        if not self.m2ee.config.lookup_in_mxjar_repo(version):
            if not self.m2ee.config.get_first_writable_mxjar_repo():
                return self.say("Runtime is not present and can't be saved anywhere.")
            self.m2ee.download_and_unpack_runtime(version)

            self.m2ee.unpack('model.mda')
            return self.say('Runtime downloaded and Model unpacked.')

        return self.say('Model unpacked.')

    def emptydb(self):
        if not self.m2ee.config.is_using_postgresql():
            return self.say("Only PostgreSQL is supported right now.")

        (pid_alive, m2ee_alive) = self.m2ee.check_alive()
        if pid_alive or m2ee_alive:
            return self.say("The app is still running, refusing to empty the database.")

        m2ee.pgutil.emptydb(self.m2ee.config)
        return self.say("Database is emtpy now.")

    def config(self):
        if request.method == 'GET':
            return jsonify(self.m2ee.config._conf['mxruntime'])

        configs = [
            'DatabaseHost',
            'DatabaseName',
            'DatabaseUserName',
            'DatabasePassword',
            'DatabaseType',
            'MicroflowConstants'
        ]
        for key in configs:
            if key in request.form:
                self.m2ee.config._conf['mxruntime'][key] = request.form[key]
        return self.say("Config set.")


app = Flask(__name__)
if __name__ == "__main__":
    api = REST(app)
    api.run()
