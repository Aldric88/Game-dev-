from apscheduler.schedulers.background import BackgroundScheduler
from auth_service.database import users_collection
from auth_service.config.plans import PLAN_LIMITS


async def reset_monthly_credits():

    users = users_collection.find()

    async for user in users:

        plan = user.get("plan", "free")

        credit_limit = PLAN_LIMITS.get(plan, 10)

        if credit_limit == -1:
            continue

        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "credits": credit_limit,
                    "credits_used_this_month": 0
                }
            }
        )


def start_scheduler():

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        reset_monthly_credits,
        "cron",
        day=1,
        hour=0,
        minute=0
    )

    scheduler.start()