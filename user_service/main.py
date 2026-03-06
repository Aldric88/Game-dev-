from fastapi import FastAPI

app = FastAPI(title="User Service")

@app.get("/")
def root():
    return {"message": "User Service Running"}