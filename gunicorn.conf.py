# gunicorn.conf.py
import multiprocessing

bind = "127.0.0.1:8003"             # <-- backend port (private)
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 300
graceful_timeout = 30
keepalive = 5

# Optional logging
accesslog = "/var/log/gunicorn/arsinoe_access.log"
errorlog  = "/var/log/gunicorn/arsinoe_error.log"
loglevel  = "info"

