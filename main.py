from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

from views import home

app = FastAPI(
    title="ARSINOE data server",
    version="0.4.2",
    description="ARSINOE data server OpenAPI schema",
)

def configure():
    os.makedirs('uploads', exist_ok=True)
    app.mount('/static', StaticFiles(directory='static'), name='static')
    app.mount("/uploads", StaticFiles(directory='uploads'), name="uploads")
    app.include_router(home.router)

if __name__ == '__main__':
    configure()
    #uvicorn.run(app, host="0.0.0.0", port=8080)
    uvicorn.run(app, port=8000, host='127.0.0.1')
    #uvicorn.run(app, port=80,   host='127.0.0.1')
    #uvicorn.run(app, port=8000, host='156.148.14.177')
else:
    configure()
