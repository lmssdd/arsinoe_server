# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
reload = False
timeout = 300  # Example: 5 minutes
accesslog = "access.log"  # Relative path (recommended)
errorlog = "error.log"  # Relative path (recommended)
# OR absolute paths:
# accesslog = "/apps/app_repo/arsinoe_server/access.log"
# errorlog = "/apps/app_repo/arsinoe_server/error.log"
# ... other settings