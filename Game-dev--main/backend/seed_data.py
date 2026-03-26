"""
Seed script — creates 10 test users + 200 dummy projects for ML testing.
Each user has a game-type personality, cross-user likes, and search history
so the recommendation engine returns meaningful personalized results.

Run from backend directory:
    python seed_data.py
"""

import asyncio
import random
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

# ── Config ───────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME   = "game_ai_platform"
PASSWORD  = "12345678"


def hash_password(plain: str) -> str:
    from app.core.security import hash_password as _hash
    return _hash(plain)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Game catalogue ────────────────────────────────────────────────────────────
GAMES = {
    "platformer": [
        ("Mario Clone",         "Classic side-scrolling platformer with coins and enemies"),
        ("Jungle Runner",       "Run through a jungle dodging obstacles and collecting gems"),
        ("Sky Jump",            "Jump across floating platforms in the clouds"),
        ("Cave Explorer",       "Explore dark caves and collect treasures"),
        ("Pixel Platformer",    "Retro pixel art platformer with multiple worlds"),
        ("Desert Run",          "Run through desert levels avoiding cacti and scorpions"),
        ("Ice World",           "Slippery ice physics platformer with snow enemies"),
        ("Gravity Flip",        "Flip gravity to navigate tricky levels"),
        ("Neon Runner",         "Fast-paced neon-styled auto-runner"),
        ("Forest Hop",          "Hop between trees and vines in a forest platformer"),
        ("Lava Land",           "Platform over lava pools in this fiery side-scroller"),
        ("Cloud Jumper",        "Jump between disappearing clouds to reach the top"),
    ],
    "flappy": [
        ("Flappy Duck",         "Tap to keep a duck flying between pipes"),
        ("Pipe Dreams",         "Navigate through endless pipes without touching them"),
        ("Sky Bird",            "Help a tiny bird soar through obstacles"),
        ("Flutter Wings",       "Flappy style game with butterfly theme"),
        ("Chopper Run",         "Fly a tiny helicopter through narrow gaps"),
        ("Balloon Escape",      "Keep your balloon floating through cave passages"),
        ("Rocket Dodge",        "Pilot a rocket through asteroid fields by tapping"),
    ],
    "snake": [
        ("Classic Snake",       "Eat food and grow longer without hitting walls"),
        ("Neon Snake",          "Glowing neon snake in a dark arena"),
        ("Color Snake",         "Match snake color to food for bonus points"),
        ("Snake Mania",         "Snake with power-ups and multiple levels"),
        ("Worm Feast",          "Slither and eat your way to the top"),
        ("Arctic Snake",        "Snake game on a slippery ice grid"),
        ("Rainbow Serpent",     "Collect rainbow orbs to change your snake color"),
    ],
    "space_shooter": [
        ("Alien Invasion",      "Defend Earth from waves of alien spaceships"),
        ("Space Wars",          "Epic space battles with upgradeable ships"),
        ("Galaxy Defender",     "Protect the galaxy from meteor showers"),
        ("Asteroid Storm",      "Blast through asteroid fields in deep space"),
        ("Star Blaster",        "Shoot down enemy fighters in outer space"),
        ("Nova Strike",         "High speed space shooter with boss battles"),
        ("Cosmic Raiders",      "Raid enemy fleets across the cosmos"),
        ("Nebula Fighter",      "Dogfight through colorful nebula clouds"),
    ],
    "tower_defense": [
        ("Castle Defense",      "Build towers to defend your castle from enemies"),
        ("Tower Wars",          "Strategic tower placement to stop invaders"),
        ("Kingdom Guard",       "Protect the kingdom with archers and cannons"),
        ("Archer's Keep",       "Deploy archers to stop the goblin horde"),
        ("Fortress Hold",       "Last line of defense against the enemy army"),
        ("Jungle Defense",      "Set traps in the jungle to stop the invasion"),
        ("Ice Tower",           "Freeze enemies with ice towers in a winter fortress"),
    ],
    "fighting": [
        ("Street Brawl",        "One-on-one street fighting with combos"),
        ("Pixel Fighter",       "Retro 2D fighting game with special moves"),
        ("Combat Arena",        "Battle opponents in an arena fighting game"),
        ("Shadow Fight",        "Silhouette-style martial arts fighting game"),
        ("Brawl Club",          "Beat up waves of enemies in a brawler"),
        ("Rooftop Rumble",      "Fight on rooftops with environmental hazards"),
        ("Dojo Clash",          "Martial arts tournament with unique fighters"),
    ],
    "survival": [
        ("Zombie Horde",        "Survive endless waves of zombies with limited ammo"),
        ("Wave Survivor",       "Hold out against increasingly difficult waves"),
        ("Last Stand",          "You are the last survivor against monster hordes"),
        ("Night Survival",      "Survive the night against creatures in the dark"),
        ("Vampire Survivors Clone", "Survive hordes using auto-attacking weapons"),
        ("Island Survivor",     "Gather resources and survive on a deserted island"),
        ("Bunker Defense",      "Defend your underground bunker from mutants"),
        ("Forest Survival",     "Craft tools and survive in a hostile forest"),
    ],
    "racing": [
        ("Speed Racer",         "Top-down racing game with turbo boosts"),
        ("Drift King",          "Master the art of drifting in tight corners"),
        ("Road Rush",           "Dodge traffic on a busy highway at high speed"),
        ("Kart Race",           "Fun kart racing with power-ups and shortcuts"),
        ("Rally Run",           "Off-road rally racing through rough terrain"),
        ("Pixel GP",            "Pixel art Formula style racing game"),
        ("Night Drive",         "Race through neon-lit city streets at night"),
        ("Boat Race",           "High-speed boat racing through river obstacles"),
    ],
    "puzzle": [
        ("Match Master",        "Match 3 puzzle game with colorful gems"),
        ("Block Puzzle",        "Fit falling blocks to clear lines"),
        ("Color Match",         "Match colors before the timer runs out"),
        ("Slide Puzzle",        "Rearrange tiles to complete the picture"),
        ("Brain Teaser",        "Collection of mind-bending logic puzzles"),
        ("Number Merge",        "Merge numbers to reach the target score"),
        ("Flow Connect",        "Connect matching colors without crossing lines"),
        ("Hex Twist",           "Rotate hexagonal tiles to form patterns"),
        ("Word Grid",           "Find hidden words in a letter grid"),
    ],
    "rpg": [
        ("Dragon Quest",        "Embark on a quest to defeat the dragon king"),
        ("Dungeon Crawler",     "Explore procedurally generated dungeons with loot"),
        ("Hero's Journey",      "Level up your hero and save the world"),
        ("Dark Forest RPG",     "Survive a haunted forest with RPG mechanics"),
        ("Pixel Quest",         "Retro top-down RPG with towns and bosses"),
        ("Sword & Spell",       "Dual-class RPG with melee and magic combat"),
        ("The Lost Kingdom",    "Rebuild a fallen kingdom in this RPG adventure"),
    ],
    "topdown": [
        ("Top Down Shooter",    "Twin-stick top-down shooter with many enemies"),
        ("GTA Micro",           "Top-down open world crime game"),
        ("Twin Stick Arena",    "Overhead arena shooter with power-ups"),
        ("Overhead Adventure",  "Top-down adventure game with dungeons"),
        ("Zombie Overhead",     "Overhead view zombie survival game"),
        ("Wasteland Roamer",    "Roam a post-apocalyptic wasteland top-down"),
        ("Heist Run",           "Top-down stealth heist game with guards"),
    ],
    "shooter": [
        ("Gun Blaster",         "Side-scrolling shooter with weapon upgrades"),
        ("Bullet Hell",         "Dodge thousands of bullets in this shooter"),
        ("Rapid Fire",          "Fast-paced shooting gallery game"),
        ("Target Practice",     "Shoot moving targets for high score"),
        ("Run and Gun",         "Classic run and gun side-scroller"),
        ("Metal Slug Clone",    "Action run-and-gun inspired by Metal Slug"),
        ("Gunship",             "Control a gunship blasting ground forces"),
    ],
    "arcade": [
        ("Classic Arcade",      "Old school arcade game with high score chasing"),
        ("Score Rush",          "Endless arcade game for maximum score"),
        ("Quick Tap",           "Reaction-based tap game with increasing speed"),
        ("Retro Blaster",       "Retro-style arcade blaster game"),
        ("Coin Pusher",         "Push coins off the edge in this arcade classic"),
        ("Whack Attack",        "Whack targets as fast as they appear"),
    ],
    "clicker": [
        ("Cookie Factory",      "Click cookies and buy upgrades to bake more automatically"),
        ("Idle Miner",          "Mine resources by clicking and hire workers to automate"),
        ("Tap Empire",          "Build a business empire one tap at a time"),
        ("Click Dungeon",       "Click to attack monsters and earn gold for upgrades"),
        ("Idle Kingdom",        "Watch your kingdom grow passively with smart upgrades"),
    ],
    "rhythm": [
        ("Beat Tap",            "Tap falling notes in time with the music to score"),
        ("Piano Rush",          "Hit the black tiles before they pass in this piano game"),
        ("Rhythm Battle",       "Challenge opponents in a beat-matching musical duel"),
        ("Note Drop",           "Catch falling notes on the beat for combos"),
        ("DJ Dash",             "Scratch and mix beats as a virtual DJ"),
    ],
    "sports": [
        ("Penalty Kick",        "Aim and shoot penalties against an AI goalkeeper"),
        ("Street Basketball",   "Dribble and shoot hoops in a street basketball game"),
        ("Table Tennis",        "Fast-paced ping pong with spin and smash mechanics"),
        ("Mini Golf",           "Putt through creative obstacle courses in mini golf"),
        ("Head Soccer",         "Use your giant head to score soccer goals"),
    ],
    "simulation": [
        ("Farm Life",           "Plant crops water them and harvest to grow your farm"),
        ("City Planner",        "Build roads and place buildings to grow a city"),
        ("Cafe Manager",        "Run a busy cafe serve customers and upgrade equipment"),
        ("Virtual Pet",         "Feed play and care for your digital creature"),
        ("Space Colony",        "Manage resources and build a colony on a new planet"),
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
    "clicker":       ["click to earn", "buy upgrades", "passive income", "prestige", "auto clicker"],
    "rhythm":        ["tap on beat", "note highway", "combo multiplier", "timing accuracy", "music sync"],
    "sports":        ["score goals", "compete against ai", "timer", "scoreboard", "match"],
    "simulation":    ["manage resources", "build structures", "upgrade", "produce goods", "time management"],
}

FRAMEWORKS = ["phaser", "phaser", "phaser", "vanilla"]

# ── User personalities — each user favours certain game types ─────────────────
# Weight 3 = strong preference, 1 = occasional
USER_PROFILES = [
    # (username suffix, {game_type: weight}, search_terms)
    ("01", {"platformer": 3, "puzzle": 2, "arcade": 1},          ["platformer", "mario", "jump puzzle"]),
    ("02", {"space_shooter": 3, "shooter": 2, "topdown": 1},     ["space shooter", "bullet hell", "alien"]),
    ("03", {"rpg": 3, "survival": 2, "tower_defense": 1},        ["rpg quest", "dungeon", "survival waves"]),
    ("04", {"puzzle": 3, "arcade": 2, "flappy": 1},              ["puzzle game", "match 3", "arcade"]),
    ("05", {"survival": 3, "tower_defense": 2, "fighting": 1},   ["zombie survival", "tower defense", "horde"]),
    ("06", {"racing": 3, "fighting": 2, "arcade": 1},            ["racing game", "drift", "fighting"]),
    ("07", {"snake": 3, "flappy": 2, "arcade": 1},               ["snake game", "flappy bird", "tap game"]),
    ("08", {"topdown": 3, "shooter": 2, "space_shooter": 1},     ["top down", "twin stick", "run and gun"]),
    ("09", {"rpg": 2, "platformer": 2, "puzzle": 2},             ["rpg platformer", "adventure", "pixel game"]),
    ("10", {"fighting": 2, "survival": 2, "racing": 2},          ["brawler", "fighting game", "survive"]),
]


def pick_game_type_for_user(profile_weights: dict) -> str:
    types = list(profile_weights.keys())
    weights = list(profile_weights.values())
    return random.choices(types, weights=weights, k=1)[0]


def make_project(owner: dict, game_type: str, name: str, desc: str,
                 is_public: bool, rng: random.Random) -> dict:
    plays = rng.randint(10, 300) if is_public else 0
    likes = rng.randint(0, plays // 4 + 1) if is_public else 0
    mechanics = rng.sample(MECHANICS_MAP[game_type], k=min(3, len(MECHANICS_MAP[game_type])))
    framework = rng.choice(FRAMEWORKS)
    ts = now_iso()
    return {
        "project_id":    str(uuid4()),
        "user_id":       owner["user_id"],
        "name":          name,
        "description":   desc,
        "framework":     framework,
        "status":        "complete",
        "is_public":     is_public,
        "plays":         plays,
        "likes":         likes,
        "liked_by":      [],
        "design_doc": {
            "game_type":   game_type,
            "mechanics":   mechanics,
            "description": desc,
        },
        "generated_code":  {},
        "assets":          [],
        "ai_conversation": [],
        "ai_usage_logs":   [],
        "versions":        [],
        "deployment":      {"status": "not_deployed"},
        "created_at":      ts,
        "updated_at":      ts,
    }


async def seed():
    rng = random.Random(42)
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    users_col   = db["users"]
    projects_col = db["projects"]

    # ── Clear existing test data ──────────────────────────────────────────────
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

    # ── Create 10 users ───────────────────────────────────────────────────────
    users = []
    for suffix, weights, searches in USER_PROFILES:
        u = {
            "user_id":                 str(uuid4()),
            "username":                f"testuser{suffix}",
            "email":                   f"testuser{suffix}@forge.ai",
            "password_hash":           hashed_pw,
            "plan":                    "free",
            "credits":                 10,
            "credits_used_this_month": 0,
            "usage_stats":             {"api_calls": 0, "ai_tokens_used": 0},
            "search_history":          [],
            "created_at":              now_iso(),
        }
        users.append(u)

    await users_col.insert_many(users)
    print(f"Created {len(users)} users  (testuser01-testuser10 / {PASSWORD})")

    # ── Build ~20 projects per user ───────────────────────────────────────────
    # Pre-build a pool keyed by game_type for name/desc lookup
    game_pool: dict[str, list] = {gt: list(entries) for gt, entries in GAMES.items()}
    used_names: set = set()

    def pick_entry(game_type: str):
        pool = game_pool[game_type]
        rng.shuffle(pool)
        for entry in pool:
            if entry[0] not in used_names:
                used_names.add(entry[0])
                return entry
        # All used — generate a variant name
        base = pool[0]
        variant = (f"{base[0]} II", base[1])
        return variant

    all_projects = []
    for i, (user, (suffix, weights, searches)) in enumerate(zip(users, USER_PROFILES)):
        user_projects = []
        # 15 public + 5 private = 20 per user
        for j in range(20):
            is_public = j < 15
            gt = pick_game_type_for_user(weights)
            name, desc = pick_entry(gt)
            p = make_project(user, gt, name, desc, is_public, rng)
            user_projects.append(p)
        all_projects.extend(user_projects)

    # ── Seed cross-user likes ─────────────────────────────────────────────────
    # Each user likes 8-12 public projects from OTHER users
    # based on their personality weights
    public_projects = [p for p in all_projects if p["is_public"]]
    for i, (user, (suffix, weights, searches)) in enumerate(zip(users, USER_PROFILES)):
        uid = user["user_id"]
        # candidate projects: public, not owned by this user
        candidates = [p for p in public_projects if p["user_id"] != uid]
        # prefer projects matching personality game types
        preferred = [p for p in candidates if p["design_doc"]["game_type"] in weights]
        others    = [p for p in candidates if p not in preferred]
        rng.shuffle(preferred)
        rng.shuffle(others)
        # pick 6-8 from preferred types + 2-3 random
        to_like = preferred[:rng.randint(6, 8)] + others[:rng.randint(2, 3)]
        for p in to_like:
            if uid not in p["liked_by"]:
                p["liked_by"].append(uid)
                p["likes"] = len(p["liked_by"])

    await projects_col.insert_many(all_projects)

    # ── Seed search history ───────────────────────────────────────────────────
    for user, (suffix, weights, searches) in zip(users, USER_PROFILES):
        history = []
        for term in searches:
            history.append({
                "query":           term,
                "predicted_type":  list(weights.keys())[0],
                "confidence":      round(rng.uniform(0.65, 0.95), 2),
                "timestamp":       now_iso(),
            })
        await users_col.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"search_history": history}}
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    public_count  = sum(1 for p in all_projects if p["is_public"])
    private_count = len(all_projects) - public_count
    type_counts: dict = {}
    for p in all_projects:
        gt = p["design_doc"]["game_type"]
        type_counts[gt] = type_counts.get(gt, 0) + 1

    print(f"Created {len(all_projects)} projects  ({public_count} public, {private_count} private)")
    print()
    print("Distribution by game type:")
    for gt, cnt in sorted(type_counts.items()):
        print(f"  {gt:<20} {cnt}")

    print()
    print("Top 5 by likes:")
    top = sorted(public_projects, key=lambda p: p["likes"], reverse=True)[:5]
    for p in top:
        print(f"  {p['likes']:>2} likes  {p['name']}  ({p['design_doc']['game_type']})")

    print()
    print("Search history seeded per user:")
    for user, (suffix, weights, searches) in zip(users, USER_PROFILES):
        print(f"  testuser{suffix}  {searches}")

    client.close()
    print()
    print("Done. Login with testuser01@forge.ai / 12345678")


if __name__ == "__main__":
    asyncio.run(seed())
