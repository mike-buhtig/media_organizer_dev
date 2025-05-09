Coding Conventions for Media Organizer ProjectThis document outlines coding conventions and directives for the Media Organizer project to ensure maintainable, flexible, and consistent code across all scripts (Season_Episode_builder.py, file_organizer.py, etc.). These conventions prioritize dynamic configuration over hard-coding to prevent errors and simplify future extensions.
Related Documents
This document must be used in conjunction with:

plans/requirements.md: Defines functional requirements and configuration structure (e.g., paths.txt).
plans/script_relationships.md: Describes script interactions and dependencies.Failure to consult all three documents may result in non-compliant code (e.g., hard-coding providers).

Governance Rules

No Unauthorized Deletions: No sections, settings, or content in this document, other governing documents (requirements.md, script_relationships.md), or configuration files (paths.txt, paths.example.txt) may be removed without explicit approval from the project engineer. All content serves a purpose, and unauthorized deletions may lead to loss of critical functionality or data.
Preserve Script Logic: Scripts (Season_Episode_builder.py, file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py, providers/.py) are the primary storage of functional logic for the project. No logic within these scripts may be altered or removed, even if it appears unnecessary, without explicit approval from the project engineer. All logic must remain available to support current and future functionality.
Read All Documents Before Changes: All governing documents (coding_conventions.md, requirements.md, script_relationships.md) and configuration files (paths.txt, paths.example.txt) must be fully reviewed before making any changes to identify existing content, ensure compliance, and avoid conflicts or deletions.
Report Conflicts: If a conflict is found between documents, within a document, or in script logic, no changes may be made. The conflict must be reported to the project engineer for resolution.

Directive: No Hard-Coding of Providers
Hard-coding of providers is strictly prohibited. Scripts must not include static lists of providers, provider names, or provider module references. Instead, all provider-related functionality must be driven by conventions and configuration files, specifically config/paths.txt. This ensures:

Flexibility to add, remove, or rename providers without modifying script code.
Consistency with paths.txt configuration, avoiding mismatches.
Reduced maintenance and fewer bugs from outdated hard-coded lists.

Why Avoid Hard-Coding?Hard-coding providers, as seen in Season_Episode_builder.py with providers = [("tvmazef", ...)], caused issues like:

Mismatched provider names between script and paths.txt, leading to no providers being called.
Inability to add new providers without code changes.
Maintenance overhead when renaming providers.

Configuration Files

config/paths.txt: Contains project configuration, including [meta_providers], [series], and provider-specific settings (e.g., API keys, scrape delays).
[meta_providers]: Lists providers and their status (e.g., tvmaze=enabled).
[series]: Maps series names to their file paths (e.g., series_name_1 = The A-Team, series_path_1 = D:/NEXT PVR/RecordingDirectory/The A-Team) for use by series_folder_crawler.py and file_organizer.py.


config/paths.example.txt: A template identical to paths.txt except for placeholder settings (e.g., your_tvmaze_api_key, SCRAPE_DELAY). Users copy this to create paths.txt and fill in valid settings.

Provider Naming and Loading Conventions
The following conventions govern how scripts load and interact with function-based providers (e.g., tvmaze.py). These apply to all scripts that fetch metadata, such as Season_Episode_builder.py.
1. Provider Configuration in paths.txt

Providers are defined in the [meta_providers] section of config/paths.txt.
Format: =, where:
: Unique provider identifier (e.g., tvmaze, tmdb, trakt, rotten_tomatoes). Each provider represents a distinct metadata source, ensuring no name collisions.
: enabled or disabled.


Priority Order: The order of providers in [meta_providers] (top to bottom) defines their preference for metadata merging and episode naming in Season_Episode_builder.py, series_folder_crawler.py, and file_organizer.py. For example:[meta_providers]
tvmaze=enabled
tmdb=enabled
trakt=enabled
rotten_tomatoes=enabled

tvmaze (first) has the highest priority, rotten_tomatoes (last) the lowest, due to its crowd-sourced nature, though it’s valuable for cases like Samsung TV Plus episode titles/overviews.
This order is preserved in data//.json and used by downstream scripts to select episode names (e.g., series_name_SxxEyy_episode-name).
Scripts must read [meta_providers] to determine which providers are enabled and their priority.
Only providers with enabled status and a corresponding scripts/providers/.py are processed.

2. Provider Module Naming

Function-based providers are Python modules located in scripts/providers/.
Module name format: .py, where  matches the [meta_providers] key (e.g., tvmaze.py for tvmaze=enabled).
Each module must export a get_metadata function with the signature:def get_metadata(series_name: str, config: ConfigParser) -> None


Writes metadata to tmp/.json.
Example: For tvmaze=enabled, the module is scripts/providers/tvmaze.py.

3. Dynamic Provider Loading

Scripts must dynamically import provider modules based on [meta_providers].
Steps:
Iterate over [meta_providers] keys in order (top to bottom).
For each =enabled:
Import the module providers. using importlib.import_module.
Access the get_metadata function.
Call get_metadata(series_name, config) for enabled providers with existing modules, respecting priority order for metadata merging.




Example code:import importlib
provider_data = []
for provider_name, status in config["meta_providers"].items():
    if status == "enabled":
        try:
            module = importlib.import_module(f"providers.{provider_name}")
            get_metadata = module.get_metadata
            get_metadata(series_name, config)
            # Process tmp/<name>.json
        except ImportError as e:
            print(f"Failed to import provider {provider_name}: {e}")


This eliminates hard-coded lists like providers = [("tvmaze", ...)].

4. Temporary File Naming and Cleanup

Providers write metadata to tmp/.json, where  matches the [meta_providers] key (e.g., tmp/tvmaze.json).
Before writing, scripts must delete tmp/.json if it exists to prevent stale data.
The TEMP_FOLDER (e.g., tmp) is defined in paths.txt’s [general] section.
Example:temp_file = os.path.join(temp_folder, f"{provider_name}.json")
if os.path.exists(temp_file):
    os.remove(temp_file)



5. Error Handling

Module Import Errors: If .py is missing, log the error to logs//builder.log and continue with other providers.
Missing Output Files: If tmp/.json is missing, log and skip the provider.
Invalid Config: If [meta_providers] is missing or empty, log a warning and exit gracefully.
Example:if "meta_providers" not in config:
    log_message(log_path, "No [meta_providers] section in paths.txt. Exiting.")
    return



6. Logging

All provider-related actions (loading, errors, file reads) must be logged to logs//builder.log.
Use the LOG_PATH from paths.txt’s [general] section (e.g., logs).
Include timestamps and clear messages (e.g., Failed to import provider tvmaze: Module not found).

7. Future-Proofing

Adding a new provider requires:
Adding =enabled to paths.txt’s [meta_providers] in the desired priority position.
Creating .py in scripts/providers/ with a get_metadata function.


Adding a new series requires:
Adding series_name_X = , series_path_X =  to paths.txt’s [series] section.


No script changes are needed, as providers and series are loaded dynamically.
Example: To add an imdb provider or a new series:[meta_providers]
imdb=enabled
[series]
series_name_8 = New Series
series_path_8 = D:/Recordings/New Series



Implementation Notes

Use Python’s importlib.import_module for dynamic imports to avoid hard-coded import statements.
Validate provider modules by checking for the get_metadata function before calling it.
Ensure scripts handle partial failures (e.g., one provider fails) without crashing.
Regularly review paths.txt and paths.example.txt to ensure alignment with conventions.
Season_Episode_builder.py outputs raw provider data in data//.json, with normalization handled by series_folder_crawler.py.

References

plans/requirements.md: Defines paths.txt structure, provider requirements, and JSON output format for Season_Episode_builder.py.
plans/script_relationships.md: Describes provider and series interactions with scripts.
config/paths.example.txt: Provides example [meta_providers] and [series] settings.

Enforcement

All scripts must be reviewed to ensure compliance with these conventions.
Hard-coded provider or series lists, or unauthorized logic changes, will be rejected during code reviews.
Update existing scripts (e.g., Season_Episode_builder.py) to remove hard-coded providers and adopt dynamic loading.

Provider Precedence

The order in [meta_providers] determines precedence for downstream naming and overview selection, with tvmaze as the primary source, followed by tmdb, trakt, and rotten_tomatoes.
Merged metadata in data/<series_slug>/<series_name>.json includes all providers’ data for each field, with provider keys ordered as in [meta_providers] to reflect priority for downstream scripts.

Logging (Season_Episode_builder.py)

Scripts log to logs/<series_slug>/<series_slug>_builder.log for Season_Episode_builder.py actions (e.g., logs/ax_men/ax_men_builder.log).
Providers log to logs/<series_slug>/<series_slug>_provider.log for provider-specific actions (e.g., logs/ax_men/ax_men_provider.log).
Both logs are stored in logs/<series_slug>/ in append mode.
Providers use Season_Episode_builder.py’s logging mechanism for consistent formatting.
These conventions apply only to Season_Episode_builder.py and its providers (tvmaze.py, tmdb.py, trakt.py, rotten_tomatoes.py).
Note: Logging for downstream scripts (file_organizer.py, series_folder_crawler.py, kodi_db_exporter.py) will be defined in future updates. This note will be removed when those directives are complete.

