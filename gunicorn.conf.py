# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"  # Address and port to bind to
workers = multiprocessing.cpu_count() * 2 + 1  # Recommended number of workers
worker_class = "uvicorn.workers.UvicornWorker" # Use Uvicorn workers
reload = False  # Set to True for development, False for production
accesslog = "/apps/app_repo/arsinoe_server/access.log"  # Path to access log file
errorlog = "/apps/app_repo/arsinoe_server/error.log"  # Path to error log file
# timeout = 30  # Request timeout in seconds (optional)
# graceful_timeout = 30 # Graceful shutdown timeout (optional)
# keepalive = 2 # Keep-alive connections (optional)
