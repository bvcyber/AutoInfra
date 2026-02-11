import subprocess
import logging
import threading

logger = logging.getLogger("backend-logs")

def run_command_and_read_output(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    decodedOutput = output.decode("utf-8")
    logger.debug(f"RUN_COMMAND_AND_READ_OUTPUT: Output: {decodedOutput}")
    return decodedOutput

def run_command_and_get_exit_code(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    code = process.returncode
    logger.debug(f"RUN_COMMAND_AND_GET_EXIT_CODE: Code: {code}")
    return code

def run_async_command(targetFunction, *args):
    try:
        thread = threading.Thread(target=targetFunction, args=(args))
        logger.debug(f"Run async command - success")
        thread.start()
    except Exception as e:
        logger.error(f"RUN_ASYNC_COMMAND: {targetFunction} with {args} did NOT start. Error: {e}")
