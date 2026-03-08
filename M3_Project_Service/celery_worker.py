from celery import Celery
from pymongo import MongoClient

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

client = MongoClient("mongodb://localhost:27017")
db = client["game_db"]
projects = db["projects"]

@celery_app.task
def generate_game(project_id):

    print(f"Generating game for project: {project_id}")

    projects.update_one(
        {"project_id": project_id},
        {"$set": {"status": "completed"}}
    )

    return "done"