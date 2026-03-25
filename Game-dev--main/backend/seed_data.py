"""
Seed script — creates 10 test users + 100 dummy projects for ML testing.
Run from backend directory:
    python seed_data.py
"""

import asyncio
import random
from datetime import datetime, timezone
from uuid import uuid4

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

# ── Config ──────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME   = "game_ai_platform"
PASSWORD  = "12345678"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

# ── Game type data ───────────────────────────────────────────────────────────
GAMES = {
    "platformer": [
        ("Mario Clone",        "Classic side-scrolling platformer with coins and enemies"),
        ("Jungle Runner",      "Run through a jungle dodging obstacles and collecting gems"),
        ("Sky Jump",           "Jump across floating platforms in the clouds"),
        ("Cave Explorer",      "Explore dark caves and collect treasures"),
        ("Pixel Platformer",   "Retro pixel art platformer with multiple worlds"),
        ("Desert Run",         "Run through desert levels avoiding cacti and scorpions"),
        ("Ice World",          "Slippery ice physics platformer with snow enemies"),
        ("Gravity Flip",       "Flip gravity to navigate tricky levels"),
        ("Neon Runner",        "Fast-paced neon-styled auto-runner"),
    ],
    "flappy": [
        ("Flappy Duck",        "Tap to keep a duck flying between pipes"),
        ("Pipe Dreams",        "Navigate through endless pipes without touching them"),
        ("Sky Bird",           "Help a tiny bird soar through obstacles"),
        ("Flutter Wings",      "Flappy style game with butterfly theme"),
        ("Chopper Run",        "Fly a tiny helicopter through narrow gaps"),
    ],
    "snake": [
        ("Classic Snake",      "Eat food and grow longer without hitting walls"),
        ("Neon Snake",         "Glowing neon snake in a dark arena"),
        ("Color Snake",        "Match snake color to food for bonus points"),
        ("Snake Mania",        "Snake with power-ups and multiple levels"),
        ("Worm Feast",         "Slither and eat your way to the top"),
    ],
    "space_shooter": [
        ("Alien Invasion",     "Defend Earth from waves of alien spaceships"),
        ("Space Wars",         "Epic space battles with upgradeable ships"),
        ("Galaxy Defender",    "Protect the galaxy from meteor showers"),
        ("Asteroid Storm",     "Blast through asteroid fields in deep space"),
        ("Star Blaster",       "Shoot down enemy fighters in outer space"),
        ("Nova Strike",        "High speed space shooter with boss battles"),
    ],
    "tower_defense": [
        ("Castle Defense",     "Build towers to defend your castle from enemies"),
        ("Tower Wars",         "Strategic tower placement to stop invaders"),
        ("Kingdom Guard",      "Protect the kingdom with archers and cannons"),
        ("Archer's Keep",      "Deploy archers to stop the goblin horde"),
        ("Fortress Hold",      "Last line of defense against the enemy army"),
    ],
    "fighting": [
        ("Street Brawl",       "One-on-one street fighting with combos"),
        ("Pixel Fighter",      "Retro 2D fighting game with special moves"),
        ("Combat Arena",       "Battle opponents in an arena fighting game"),
        ("Shadow Fight",       "Silhouette-style martial arts fighting game"),
        ("Brawl Club",         "Beat up waves of enemies in a brawler"),
    ],
    "survival": [
        ("Zombie Horde",       "Survive endless waves of zombies with limited ammo"),
        ("Wave Survivor",      "Hold out against increasingly difficult waves"),
        ("Last Stand",         "You are the last survivor against monster hordes"),
        ("Night Survival",     "Survive the night against creatures in the dark"),
        ("Vampire Survivors Clone", "Survive hordes using auto-attacking weapons"),
        ("Island Survivor",    "Gather resources and survive on a deserted island"),
    ],
    "racing": [
        ("Speed Racer",        "Top-down racing game with turbo boosts"),
        ("Drift King",         "Master the art of drifting in tight corners"),
        ("Road Rush",          "Dodge traffic on a busy highway at high speed"),
        ("Kart Race",          "Fun kart racing with power-ups and shortcuts"),
        ("Rally Run",          "Off-road rally racing through rough terrain"),
        ("Pixel GP",           "Pixel art Formula style racing game"),
    ],
    "puzzle": [
        ("Match Master",       "Match 3 puzzle game with colorful gems"),
        ("Block Puzzle",       "Fit falling blocks to clear lines"),
        ("Color Match",        "Match colors before the timer runs out"),
        ("Slide Puzzle",       "Rearrange tiles to complete the picture"),
        ("Brain Teaser",       "Collection of mind-bending logic puzzles"),
        ("Number Merge",       "Merge numbers to reach the target score"),
        ("Flow Connect",       "Connect matching colors without crossing lines"),
    ],
    "rpg": [
        ("Dragon Quest",       "Embark on a quest to defeat the dragon king"),
        ("Dungeon Crawler",    "Explore procedurally generated dungeons with loot"),
        ("Hero's Journey",     "Level up your hero and save the world"),
        ("Dark Forest RPG",    "Survive a haunted forest with RPG mechanics"),
        ("Pixel Quest",        "Retro top-down RPG with towns and bosses"),
    ],
    "topdown": [
        ("Top Down Shooter",   "Twin-stick top-down shooter with many enemies"),
        ("GTA Micro",          "Top-down open world crime game"),
        ("Twin Stick Arena",   "Overhead arena shooter with power-ups"),
        ("Overhead Adventure", "Top-down adventure game with dungeons"),
        ("Zombie Overhead",    "Overhead view zombie survival game"),
    ],
    "shooter": [
        ("Gun Blaster",        "Side-scrolling shooter with weapon upgrades"),
        ("Bullet Hell",        "Dodge thousands of bullets in this shooter"),
        ("Rapid Fire",         "Fast-paced shooting gallery game"),
        ("Target Practice",    "Shoot moving targets for high score"),
        ("Run and Gun",        "Classic run and gun side-scroller"),
    ],
    "arcade": [
        ("Classic Arcade",     "Old school arcade game with high score chasing"),
        ("Score Rush",         "Endless arcade game for maximum score"),
        ("Quick Tap",          "Reaction-based tap game with increasing speed"),
        ("Retro Blaster",      "Retro-style arcade blaster game"),
    ],
}

MECHANICS_MAP = {
    "platformer":    ["jump", "run", "collect coins", "avoid enemies", "double jump"],
    "flappy":        ["tap to fly", "avoid pipes", "gravity", "score counter"],
    "snake":         ["eat food", "grow longer", "avoid walls", "speed increase"],
    "space_shooter": ["shoot bullets", "dodge enemies", "power-ups", "boss fights"],
    "tower_defense": ["place towers", "upgrade towers", "wave enemies", "gold economy"],
    "fighting":      ["punch", "kick", "combo moves", "health bar", "special attacks"],
    "survival":      ["survive waves", "collect ammo", "upgrade weapons", "horde enemies"],
    "racing":        ["accelerate", "drift", "avoid traffic", "lap timer", "boost"],
    "puzzle":        ["match colors", "clear lines", "logic solving", "timer"],
    "rpg":           ["level up", "collect loot", "quest system", "turn-based combat"],
    "topdown":       ["top-down view", "shoot enemies", "navigate map", "collect items"],
    "shooter":       ["shoot", "dodge bullets", "weapon upgrades", "score multiplier"],
    "arcade":        ["high score", "lives system", "increasing difficulty", "simple controls"],
}

FRAMEWORKS = ["phaser", "phaser", "phaser", "vanilla"]  # weighted towards phaser


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def seed():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    users_col = db["users"]
    projects_col = db["projects"]

    # ── Clear existing test data ─────────────────────────────────────────────
    existing = await users_col.find(
        {"email": {"$regex": r"^testuser\d+@forge\.ai$"}},
        {"user_id": 1}
    ).to_list(length=100)
    existing_ids = [u["user_id"] for u in existing]
    if existing_ids:
        await projects_col.delete_many({"user_id": {"$in": existing_ids}})
        await users_col.delete_many({"user_id": {"$in": existing_ids}})
        print(f"Cleared {len(existing_ids)} existing test users and their projects.")

    hashed_pw = hash_password(PASSWORD)

    # ── Create 10 users ──────────────────────────────────────────────────────
    users = []
    for i in range(1, 11):
        u = {
            "user_id":   str(uuid4()),
            "username":  f"testuser{i:02d}",
            "email":     f"testuser{i:02d}@forge.ai",
            "password":  hashed_pw,
            "plan":      "free",
            "credits":   10,
            "credits_used_this_month": 0,
            "usage_stats": {"api_calls": 0, "ai_tokens_used": 0},
            "created_at": now_iso(),
        }
        users.append(u)

    await users_col.insert_many(users)
    print(f"Created {len(users)} users  (testuser01–testuser10 / {PASSWORD})")

    # ── Build 100 projects ───────────────────────────────────────────────────
    all_game_entries = []
    for game_type, entries in GAMES.items():
        for name, desc in entries:
            all_game_entries.append((game_type, name, desc))

    # Shuffle and cycle to reach 100
    random.seed(42)
    random.shuffle(all_game_entries)
    while len(all_game_entries) < 100:
        all_game_entries.extend(all_game_entries[:100 - len(all_game_entries)])
    all_game_entries = all_game_entries[:100]

    projects = []
    for idx, (game_type, name, desc) in enumerate(all_game_entries):
        owner = users[idx % 10]
        is_public = idx < 70          # first 70 are public
        plays = random.randint(0, 300) if is_public else 0
        likes = random.randint(0, plays // 3 + 1) if is_public else 0
        liked_by = random.sample(
            [u["user_id"] for u in users],
            min(likes, len(users))
        ) if likes > 0 else []

        mechanics = random.sample(MECHANICS_MAP[game_type], k=min(3, len(MECHANICS_MAP[game_type])))
        framework = random.choice(FRAMEWORKS)
        ts = now_iso()

        p = {
            "project_id":   str(uuid4()),
            "user_id":      owner["user_id"],
            "name":         name,
            "description":  desc,
            "framework":    framework,
            "status":       "complete",
            "is_public":    is_public,
            "plays":        plays,
            "likes":        likes,
            "liked_by":     liked_by,
            "design_doc": {
                "game_type":  game_type,
                "mechanics":  mechanics,
                "description": desc,
            },
            "generated_code": {},
            "assets":       [],
            "ai_conversation": [],
            "ai_usage_logs":   [],
            "versions":        [],
            "deployment":      {"status": "not_deployed"},
            "created_at":      ts,
            "updated_at":      ts,
        }
        projects.append(p)

    await projects_col.insert_many(projects)

    public_count  = sum(1 for p in projects if p["is_public"])
    private_count = len(projects) - public_count
    type_counts   = {}
    for p in projects:
        gt = p["design_doc"]["game_type"]
        type_counts[gt] = type_counts.get(gt, 0) + 1

    print(f"Created {len(projects)} projects  ({public_count} public, {private_count} private)")
    print()
    print("Distribution by game type:")
    for gt, cnt in sorted(type_counts.items()):
        print(f"  {gt:<20} {cnt}")

    print()
    print("Top 5 by plays:")
    top = sorted(projects, key=lambda p: p["plays"], reverse=True)[:5]
    for p in top:
        print(f"  {p['plays']:>3} plays  {p['name']}  ({p['design_doc']['game_type']})")

    client.close()
    print()
    print("Done. Login with testuser01@forge.ai / 12345678")


if __name__ == "__main__":
    asyncio.run(seed())
