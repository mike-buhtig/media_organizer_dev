# series_folder_crawler_v3.3.7.py
# Version 3.3.7
# Change Log:
# ...
# [3.3.6] - 2025-04-25
# - Pop match_pool immediately in Pass 1 and Pass 2.
# - Lowered Pass 3 SequenceMatcher threshold to 0.80.
# - Log Pass 3 snippets and ratios.
# - Log match_pool contents before each pass.
# - Ensure season/episode keys are unique in build_match_pool.
# [3.3.7] - 2025-04-29
# - Fixed title extraction in build_match_pool: Removed ep.get("title", "") to use only titles dictionary, preventing empty title mismatches.
# - Enhanced normalize to remove all punctuation for robust case-insensitive matching.
# - Integrated unmatched episodes into matches output with basenames, eliminated pending section.
# - Grouped .ts files by .xml basename in output.
# - Improved logging for .xml subtitle and match failures.
# - Prioritized tvmaze titles in Pass 1 matching.
# - Fixed syntax error in load_series_metadata (missing quote in encoding="utf-8").
# - Fixed syntax error in match_group_to_provider (malformed f-string in Pass 2 logging).

import os
import sys
import json
import xml.etree.ElementTree as ET
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict

# Globals
SERIES_NAME = None
ROOT_FOLDER = ""
METADATA_JSON = ""
OUTPUT_JSON = ""
LOG_FILE = ""
JSON_FOLDER = ""
LOG_PATH = ""
PASS4_THRESHOLD = 12
PASS2_THRESHOLD = 0.80
PASS3_THRESHOLD = 0.80

# ------------------
# Configuration
# ------------------

def log(msg):
    os.makedirs(LOG_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(LOG_PATH, f"series_folder_crawler_{SERIES_NAME.replace(' ', '_')}.log"), "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

# ------------------
# Text Processing
# ------------------

def normalize(s):
    if not s:
        return ""
    # Remove all punctuation and normalize
    s = re.sub(r"[^\w\s]", "", s)
    return unicodedata.normalize("NFC", s).strip().lower()

# ------------------
# Configuration
# ------------------

def load_paths(series_name):
    global ROOT_FOLDER, METADATA_JSON, OUTPUT_JSON, LOG_FILE, JSON_FOLDER, LOG_PATH, PASS4_THRESHOLD, PASS2_THRESHOLD, PASS3_THRESHOLD
    config = {}
    with open("paths.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip().strip('"')

    for i in range(1, 50):
        if config.get(f"series_name_{i}", "") == series_name:
            ROOT_FOLDER = config.get(f"series_path_{i}", "")
            JSON_FOLDER = config.get("JSON_FOLDER", ".")
            LOG_PATH = config.get("LOG_PATH", ".")
            METADATA_JSON = os.path.join(JSON_FOLDER, f"{series_name}.json")
            OUTPUT_JSON = os.path.join(JSON_FOLDER, f"{series_name.replace(' ', '_')}_Processed.json")
            PASS4_THRESHOLD = int(config.get(f"pass4_threshold_{series_name}", "12"))
            PASS2_THRESHOLD = float(config.get(f"pass2_threshold_{series_name}", "0.80"))
            PASS3_THRESHOLD = float(config.get(f"pass3_threshold_{series_name}", "0.80"))
            return
    raise ValueError(f"Series name '{series_name}' not found in paths.txt.")

def scan_xml_metadata():
    epg_groups = defaultdict(list)
    for file in os.listdir(ROOT_FOLDER):
        if file.endswith(".xml") and os.path.getsize(os.path.join(ROOT_FOLDER, file)) > 0:
            full = os.path.join(ROOT_FOLDER, file)
            try:
                tree = ET.parse(full)
                root = tree.getroot()
                subtitle = normalize(root.findtext("subtitle", ""))
                description = normalize(root.findtext("description", ""))
                key = (subtitle, description)
                epg_groups[key].append(file)
                log(f"Scanned XML: {file}, subtitle='{subtitle[:50]}...', description='{description[:50]}...'")
            except Exception as e:
                log(f"XML Parse Fail: {file} - {e}")
    return epg_groups

# ------------------
# Metadata Processing
# ------------------

def load_series_metadata():
    with open(METADATA_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def build_match_pool(meta):
    pool = []
    seen = set()
    for season in meta.get("seasons", []):
        for ep in season.get("episodes", []):
            key = (season["season_number"], ep["episode_number"])
            if key in seen:
                log(f"Duplicate season/episode: S{key[0]}E{key[1]}")
                continue
            seen.add(key)
            titles = [normalize(t) for t in ep.get("titles", {}).values() if t and "episode" not in t.lower()]
            pool.append({
                "season": season["season_number"],
                "episode": ep["episode_number"],
                "titles": titles,
                "overviews": [normalize(ep.get("overview", ""))] + [normalize(o) for o in ep.get("overviews", {}).values()],
                "title": ep.get("titles", {}).get("tvmaze", ""),
                "air_date": ep.get("air_date", "")
            })
            log(f"Added to pool: S{key[0]}E{key[1]}, titles={titles}")
    log(f"Match pool built with {len(pool)} entries: {[f'S{m['season']}E{m['episode']}: {m['titles']}' for m in pool[:5]]}...")
    return pool

# ------------------
# Matching Logic
# ------------------

def slide_window(text, size=10):
    words = text.split()
    return [' '.join(words[i:i+size]) for i in range(len(words) - size + 1)]

def token_overlap(a, b):
    return len(set(a.split()) & set(b.split()))

def match_group_to_provider(subtitle, desc, pool, pass_num):
    import logging
    logging.basicConfig(
        filename=os.path.join(LOG_PATH, f"mismatches_{SERIES_NAME.replace(' ', '_')}.log"),
        filemode="a",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s: %(message)s"
    )
    logging.debug(f"Pass {pass_num}: Processing subtitle='{subtitle}', pool size={len(pool)}")
    logging.debug(f"Pass {pass_num}: Pool titles={[f'S{m['season']}E{m['episode']}: {m['titles']}' for m in pool[:5]]}...")
    key_sub = normalize(subtitle)
    key_desc = normalize(desc)
    words = key_desc.split()

    if pass_num == 1:
        for i, m in enumerate(pool[:]):
            # Prioritize tvmaze, then others
            titles = [m["titles"][j] for j in range(len(m["titles"])) if m["titles"][j]]  # Skip empty
            if key_sub in titles or any(key_sub == t for t in titles):
                logging.info(f"Pass 1: Matched subtitle='{key_sub}' to title='{titles}', season={m['season']}, episode={m['episode']}")
                return i, m
        logging.debug(f"Pass 1: No exact match for subtitle='{key_sub}', titles checked={[t for m in pool for t in m['titles']][:10]}...")
        return None, None

    elif pass_num == 2:
        for i, m in enumerate(pool[:]):
            titles = [m["titles"][j] for j in range(len(m["titles"])) if m["titles"][j]]
            if key_sub in titles or any(key_sub == t for t in titles):
                logging.info(f"Pass 2: Exact matched subtitle='{key_sub}' to title='{titles}', season={m['season']}, episode={m['episode']}")
                return i, m
            ratios = [(t, SequenceMatcher(None, key_sub, t).ratio()) for t in titles]
            logging.debug(f"Pass 2: Ratios for subtitle='{key_sub}': {ratios}")
            for title, ratio in ratios:
                if ratio >= PASS2_THRESHOLD:
                    logging.info(f"Pass 2: Matched subtitle='{key_sub}' to title='{title}', season={m['season']}, episode={m['episode']} (ratio={ratio})")
                    return i, m
        logging.debug(f"Pass 2: No match for subtitle='{key_sub}'")
        return None, None

    elif pass_num == 3 and len(words) >= 10:
        snippets = slide_window(key_desc)
        for i, m in enumerate(pool[:]):
            for overview in m["overviews"]:
                for snippet in snippets:
                    ratio = SequenceMatcher(None, snippet, overview).ratio()
                    logging.debug(f"Pass 3: Snippet='{snippet[:50]}...', overview='{overview[:50]}...', ratio={ratio}")
                    if ratio >= PASS3_THRESHOLD:
                        logging.info(f"Pass 3: Matched snippet='{snippet}' to overview='{overview[:50]}...', season={m['season']}, episode={m['episode']}")
                        return i, m
        logging.debug(f"Pass 3: No sliding window match for description='{key_desc[:50]}...', snippets={snippets[:2]}...")
        return None, None

    elif pass_num == 4:
        for i, m in enumerate(pool[:]):
            overlaps = [(o, token_overlap(key_desc, o)) for o in m["overviews"]]
            logging.debug(f"Pass 4: Overlaps for description='{key_desc[:50]}...': {overlaps}")
            for overview, overlap in overlaps:
                if overlap >= PASS4_THRESHOLD:
                    max_subtitle_ratio = max([SequenceMatcher(None, key_sub, t).ratio() for t in m["titles"]], default=0)
                    if max_subtitle_ratio < 0.60:
                        logging.debug(f"Pass 4: Rejected match for description='{key_desc[:50]}...' to overview='{overview[:50]}...' (overlap={overlap}, subtitle_ratio={max_subtitle_ratio})")
                        continue
                    if m["season"] == 0 and max_subtitle_ratio < 0.90:
                        logging.debug(f"Pass 4: Rejected season 0 match for description='{key_desc[:50]}...' (overlap={overlap}, subtitle_ratio={max_subtitle_ratio})")
                        continue
                    logging.info(f"Pass 4: Matched description='{key_desc[:50]}...' to overview='{overview[:50]}...', season={m['season']}, episode={m['episode']} (overlap={overlap}, subtitle_ratio={max_subtitle_ratio})")
                    return i, m
        logging.debug(f"Pass 4: No token overlap match for description='{key_desc[:50]}...'")
        return None, None

    logging.info(f"Final: No match for subtitle='{key_sub}', description='{key_desc[:50]}...'")
    return None, None

def find_related_ts_files(xml_basenames):
    groups = defaultdict(list)
    for file in os.listdir(ROOT_FOLDER):
        if not file.endswith(".ts"):
            continue
        base = re.sub(r"(-0)+(?=\.ts$)", "", file[:-3])  # Remove .ts
        full = os.path.join(ROOT_FOLDER, file)
        if base + ".xml" in xml_basenames or any((base + f"{s}.xml") in xml_basenames for s in ["-0", "-0-0"]):
            groups[base].append({
                "path": full.replace("\\", "/"),
                "size": os.path.getsize(full),
                "broken": "-0" in file
            })
    return groups

def build_episode_groups():
    epg_data = scan_xml_metadata()
    provider_meta = load_series_metadata()
    match_pool = build_match_pool(provider_meta)
    results = {"seasons": []}
    all_xml = set(f for group in epg_data.values() for f in group)
    ts_groups = find_related_ts_files(all_xml)

    pairs = [(subtitle, desc, xml_list) for (subtitle, desc), xml_list in epg_data.items()]
    log(f"Processing {len(pairs)} subtitle/description pairs")
    for subtitle, desc, _ in pairs:
        log(f"Input pair: subtitle='{subtitle[:50]}...', description='{desc[:50]}...'")

    season_map = defaultdict(list)
    unmatched_pairs = pairs.copy()

    for pass_num in range(1, 5):
        log(f"Starting Pass {pass_num} with {len(unmatched_pairs)} pairs and {len(match_pool)} pool items")
        temp_unmatched = []
        for subtitle, desc, xml_list in unmatched_pairs:
            index, matched = match_group_to_provider(subtitle, desc, match_pool, pass_num)
            group = {
                "episode_meta": {
                    "subtitle": subtitle,
                    "description": desc,
                    "season": matched["season"] if matched else None,
                    "episode": matched["episode"] if matched else None,
                    "titles": matched["titles"] if matched else [],
                    "overviews": matched["overviews"] if matched else [],
                    "title": matched["title"] if matched else subtitle,
                    "air_date": matched["air_date"] if matched else ""
                },
                "files": []
            }
            for xml_file in xml_list:
                basename = xml_file.replace(".xml", "")
                ts_files = ts_groups.get(basename, [])
                if not ts_files:
                    ts_files = [{
                        "path": os.path.join(ROOT_FOLDER, f"{basename}.ts").replace("\\", "/"),
                        "size": 0,
                        "broken": False
                    }]
                group["files"].extend(ts_files)
            if matched and index is not None:
                season_map[matched["season"]].append({
                    "episode_number": matched["episode"],
                    "titles": matched["titles"],
                    "filename": group["files"][0]["path"] if group["files"] else "No .ts found",
                    "files": group["files"]
                })
                log(f"Matched: subtitle='{subtitle[:50]}...' to season={matched['season']}, episode={matched['episode']}")
                if pass_num in (1, 2):
                    match_pool.pop(index)
                    log(f"Pass {pass_num}: Popped S{matched['season']}E{matched['episode']} from match_pool, new size={len(match_pool)}")
            else:
                group["episode_meta"]["reason"] = "No match found after Pass 4"
                season_map[0].append({
                    "episode_number": len(season_map[0]) + 1,
                    "titles": [subtitle],
                    "filename": group["files"][0]["path"] if group["files"] else "No .ts found",
                    "files": group["files"]
                })
                log(f"Unmatched in Pass {pass_num}: subtitle='{subtitle[:50]}...'")
            temp_unmatched.append((subtitle, desc, xml_list))
        unmatched_pairs = temp_unmatched
        log(f"Completed Pass {pass_num}: {sum(len(episodes) for episodes in season_map.values())} episodes, {len(unmatched_pairs)} unmatched")

    for season_num, episodes in sorted(season_map.items()):
        results["seasons"].append({
            "season_number": season_num,
            "episodes": sorted(episodes, key=lambda x: x["episode_number"])
        })

    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: series_folder_crawler_v3.3.7.py \"Series Name\"")
        sys.exit(1)

    SERIES_NAME = sys.argv[1]
    load_paths(SERIES_NAME)
    log(f"Running series_folder_crawler_v3.3.7 for {SERIES_NAME}")
    grouped = build_episode_groups()
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(grouped, f, indent=2)
    log(f"Finished. Output saved to {OUTPUT_JSON}")