from celery_worker import generate_game
from fastapi import FastAPI
from pymongo import MongoClient
from datetime import datetime
import uuid

app = FastAPI()

client = MongoClient("mongodb://localhost:27017/")
db = client["game_platform"]
projects = db["projects"]

@app.get("/")
def home():
    return {"message": "M3 Project Service Running"}

@app.post("/projects")
def create_project():
    project_id = str(uuid.uuid4())

    project = {
        "project_id": project_id,
        "title": "My First Game",
        "status": "draft",
        "created_at": datetime.utcnow()
    }

    projects.insert_one(project)
    generate_game.delay(project_id)

    return {"project_id": project_id}


@app.get("/projects")
def get_projects():
    return list(projects.find({}, {"_id": 0}))


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    project = projects.find_one({"project_id": project_id}, {"_id": 0})
    if project:
        return project
    return {"error": "Project not found"}
  
@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    result = projects.delete_one({"project_id": project_id})

    if result.deleted_count == 1:
        return {"message": "Project deleted successfully"}

    return {"error": "Project not found"}
@app.put("/projects/{project_id}")
def update_project(project_id: str):
    result = projects.update_one(
        {"project_id": project_id},
        {"$set": {"status": "completed"}}
    )

    if result.modified_count == 1:
        return {"message": "Project updated successfully"}

    return {"error": "Project not found"}
@app.get("/health")
def health():
    return {"status": "service running"}