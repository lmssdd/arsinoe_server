# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"  # Listen on all interfaces, port 8000
workers = multiprocessing.cpu_count() * 2 + 1 # Recommended number of workers
worker_class = "uvicorn.workers.UvicornWorker"
reload = False # Set to True for development, False for production
accesslog = "/apps/app_repo/arsinoe_server/access.log" # Path to your access log
errorlog = "/apps/app_repo/arsinoe_server/error.log" # Path to your error log
# ... other Gunicorn settings
