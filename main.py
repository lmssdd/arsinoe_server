import json
from pathlib import Path
from fastapi import FastAPI
import uvicorn
from fastapi.staticfiles import StaticFiles

from views import home

#from fastapi_redis_cache import FastApiRedisCache, cache
#LOCAL_REDIS_URL = "redis://127.0.0.1:6379"

app = FastAPI(
    title="ARSINOE data server",
    version="0.4.2",
    description="ARSINOE data server OpenAPI schema",
)

def configure():
    app.mount('/static', StaticFiles(directory='static'), name='static')
    app.include_router(home.router)

if __name__ == '__main__':
    configure()
    uvicorn.run(app, host="0.0.0.0", port=8080)
    #uvicorn.run(app, port=8000, host='127.0.0.1')
    #uvicorn.run(app, port=80,   host='127.0.0.1')
    #uvicorn.run(app, port=8000, host='156.148.14.177')
else:
    configure()
