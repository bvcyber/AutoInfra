from flask import Flask
from custom_logger import setup_logger
import flask_cors
from deployments import Deployments
import helpers
import signal
import logging
import threading
import time
from apis.deployment_apis import deployment_apis_blueprint
from apis.scenario_apis import scenario_apis_blueprint
from apis.attack_apis import attack_apis_blueprint
from apis.auth_apis import auth_apis_blueprint
from apis.build_apis import build_apis_blueprint
from apis.topology_apis import topology_apis_blueprint
from apis.deployment_config_apis import deployment_config_apis_blueprint
from apis.update_apis import update_apis_blueprint
from apis.bloodhound_apis import bloodhound_apis_blueprint
from apis.user_sync_apis import user_sync_apis_blueprint
import os

logging.getLogger('werkzeug').setLevel(logging.WARNING)

class LogFilter(logging.Filter):
    """Create a filter to reduce excessive INFO logs"""
    def filter(self, record):
        if 'OPTIONS' in record.getMessage():
            return False
            
        if record.levelno == logging.INFO:
            important_patterns = [
                'DEPLOYMENT_RESOLVER',
                'BUILD:',
                'SHUTDOWN:',
                'ATTACK_RESOLVER',
                'Error',
                'AZURE_AUTH'
            ]
            return any(pattern in record.getMessage() for pattern in important_patterns)
        
        return record.levelno >= logging.WARNING

app = Flask(__name__)
app.secret_key = os.urandom(24)
flask_cors.CORS(app, resources={r".*": {
    "origins": "*",
    "max_age": helpers.CORS_MAX_AGE
}})
app.logger = setup_logger() # type: ignore
app.register_blueprint(deployment_apis_blueprint)
app.register_blueprint(scenario_apis_blueprint)
app.register_blueprint(attack_apis_blueprint)
app.register_blueprint(build_apis_blueprint)
app.register_blueprint(topology_apis_blueprint)
app.register_blueprint(auth_apis_blueprint)
app.register_blueprint(deployment_config_apis_blueprint)
app.register_blueprint(update_apis_blueprint)
app.register_blueprint(bloodhound_apis_blueprint)
app.register_blueprint(user_sync_apis_blueprint)

deployment_handler = Deployments()
deployment_handler.check_health_of_deployments()

def background_cleanup_thread():
    """
    Continuously monitors and deletes expired deployments.
    This ensures deployments are cleaned up even if:
    - Frontend timer doesn't fire (browser closed)
    - User never manually shuts down
    - Backend was offline during expiry time
    """
    app.logger.info("BACKGROUND_CLEANUP: Thread started - checking every 5 minutes")

    while True:
        try:
            deployment_handler.expired_deployments_handler()
            time.sleep(helpers.CLEANUP_CHECK_INTERVAL)
        except Exception as e:
            app.logger.error(f"BACKGROUND_CLEANUP: Error during cleanup: {e}")
            time.sleep(helpers.CLEANUP_ERROR_RETRY_DELAY)

cleanup_thread = threading.Thread(target=background_cleanup_thread, daemon=True, name="DeploymentCleanup")
cleanup_thread.start()
app.logger.info("STARTUP: Background cleanup thread started")

def handle_signal(signum, _frame):
    signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
    app.logger.info(f"HANDLE_SIGNAL: {signal_name} received. Cleaning up deployments before shutdown...")

    try:
        deployment_handler.cleanup_deployments_on_exit()
        app.logger.info(f"HANDLE_SIGNAL: All deployments cleaned up successfully")
    except Exception as e:
        app.logger.error(f"HANDLE_SIGNAL: Error during cleanup: {e}")

    app.logger.info(f"HANDLE_SIGNAL: Shutdown complete")
    exit(0)

is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('FLASK_ENV') == 'development'

# Only register signal handlers in production (not during debug/hot-reload)
if not is_reloader and not is_debug_mode:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    app.logger.info("STARTUP: Signal handlers registered (production mode)")
else:
    app.logger.info("STARTUP: Signal handlers disabled (debug mode with hot-reload)")

if __name__ == '__main__':
    app.run(debug=True, port=helpers.BACKEND_PORT)
