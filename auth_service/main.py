from fastapi import FastAPI
from auth_service.routes import auth_routes
from auth_service.routes import user_routes
from auth_service.utils.credit_scheduler import start_scheduler

app = FastAPI(title="Auth Service")

start_scheduler()

app.include_router(auth_routes.router)
app.include_router(user_routes.router)

@app.get("/")
def root():
    return {"message": "Auth Service Running"}