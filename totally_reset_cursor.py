import os
import shutil
import platform
import sys
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path  # Using pathlib for more robust path manipulation
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# --- Constants ---
EMOJI = {
    "SUCCESS": "✅",
    "ERROR": "❌",
    "INFO": "ℹ️",
    "RESET": "🔄",
    "WARNING": "⚠️",
    "DELETE": "🗑️",
    "CREATE": "✨",
}

# Define expected base directories for safety checks
EXPECTED_BASES = {
    "Windows": ["AppData\\Roaming", "AppData\\Local"],
    "Darwin": ["Library/Application Support", "Library/Caches", "Library/Preferences", "Library/Saved Application State", "Library/HTTPStorages"],
    "Linux": [".config", ".cache", ".local/share"]
}

# --- Helper Functions ---

def is_safe_to_delete(path_to_delete: Path, home_dir: Path, allowed_bases: list) -> bool:
    """Checks if the path is within the user's home directory and under an expected base path."""
    try:
        # Ensure the path is within the home directory
        if not path_to_delete.is_relative_to(home_dir):
            print(f"{Fore.YELLOW}{EMOJI['WARNING']} Skipping unsafe path (outside home): {path_to_delete}")
            return False

        # Ensure the path starts with one of the expected relative base paths
        relative_path = path_to_delete.relative_to(home_dir)
        if not any(str(relative_path).startswith(base) for base in allowed_bases):
             # Allow direct descendants in home (like .cursor-machine-id)
            if relative_path.parent != Path('.'):
                print(f"{Fore.YELLOW}{EMOJI['WARNING']} Skipping potentially unsafe path (unexpected location): {path_to_delete}")
                return False

    except ValueError: # Handles paths not relative to home, though the first check should catch this
         print(f"{Fore.YELLOW}{EMOJI['WARNING']} Skipping path check error (not relative to home): {path_to_delete}")
         return False
    except Exception as e:
        print(f"{Fore.YELLOW}{EMOJI['WARNING']} Error during safety check for {path_to_delete}: {e}")
        return False # Err on the side of caution

    return True

def remove_path(path_to_delete: Path, home_dir: Path, allowed_bases: list):
    """Safely removes a directory or file if it exists and is in an expected location."""
    if not path_to_delete or not path_to_delete.exists():
        return # Path doesn't exist, nothing to do

    # Crucial Safety Check
    if not is_safe_to_delete(path_to_delete, home_dir, allowed_bases):
        return # Do not proceed if safety check fails

    try:
        if path_to_delete.is_file() or path_to_delete.is_symlink():
            path_to_delete.unlink()
            print(f"{Fore.GREEN}{EMOJI['DELETE']} Deleted file: {path_to_delete}")
        elif path_to_delete.is_dir():
            shutil.rmtree(path_to_delete, ignore_errors=False) # Set ignore_errors=False for better feedback
            print(f"{Fore.GREEN}{EMOJI['DELETE']} Deleted directory: {path_to_delete}")
        else:
             print(f"{Fore.YELLOW}{EMOJI['INFO']} Skipping non-file/dir: {path_to_delete}")

    except FileNotFoundError:
        # Can happen in race conditions or if ignore_errors was true previously
         print(f"{Fore.YELLOW}{EMOJI['INFO']} Path already gone: {path_to_delete}")
    except PermissionError:
        print(f"{Fore.RED}{EMOJI['ERROR']} Permission denied deleting {path_to_delete}. Try running as administrator/sudo?")
    except OSError as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} OS error deleting {path_to_delete}: {e}")
    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} Unexpected error deleting {path_to_delete}: {e}")

def create_file_with_content(path: Path, content: str, description: str):
    """Creates a file with the given content, ensuring parent directories exist."""
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write the file
        path.write_text(content, encoding='utf-8')
        print(f"{Fore.GREEN}{EMOJI['CREATE']} {description}: {path}")
    except PermissionError:
         print(f"{Fore.RED}{EMOJI['ERROR']} Permission denied creating {path}.")
    except OSError as e:
         print(f"{Fore.RED}{EMOJI['ERROR']} OS error creating {path}: {e}")
    except Exception as e:
        print(f"{Fore.RED}{EMOJI['ERROR']} Unexpected error creating {description} at {path}: {e}")

def create_new_machine_id(path: Path):
    """Creates a new machine ID file with a random UUID."""
    new_id = str(uuid.uuid4())
    create_file_with_content(path, new_id, "Created new machine ID")

def create_new_trial_info(path: Path):
    """Creates new trial information to attempt extending the trial period."""
    try:
        now = datetime.now()
        # Generate future expiry date (e.g., 90 days from now)
        future_date = now + timedelta(days=90)
        # Timestamps in milliseconds for JSON
        start_timestamp_ms = int(now.timestamp() * 1000)
        end_timestamp_ms = int(future_date.timestamp() * 1000)

        # Create fake trial info structure (based on observed format)
        new_trial_data = {
            "trialStartTimestamp": start_timestamp_ms,
            "trialEndTimestamp": end_timestamp_ms,
            "hasUsedTrial": False, # Reset trial usage flag
            "machineId": str(uuid.uuid4()) # Generate a new machine ID specific to the trial file
        }
        content = json.dumps(new_trial_data, indent=4) # Pretty print JSON
        create_file_with_content(path, content, "Created new trial info")

    except Exception as e:
         print(f"{Fore.RED}{EMOJI['ERROR']} Failed to generate or write trial info to {path}: {e}")


# --- OS Specific Path Definitions ---

def get_os_paths(home_dir: Path) -> dict:
    """Returns a dictionary of paths to remove based on the operating system."""
    system = platform.system()
    paths = {
        "config_dirs": [],
        "cache_dirs": [],
        "state_files": [],
        "machine_id_files": [],
        "trial_file": None,
        "allowed_bases": []
    }

    if system == "Windows":
        app_data = home_dir / "AppData"
        local_app_data = app_data / "Local"
        roaming_app_data = app_data / "Roaming"
        temp_dir = local_app_data / "Temp"
        paths["allowed_bases"] = EXPECTED_BASES["Windows"]

        paths["config_dirs"] = [
            roaming_app_data / "Cursor",
            roaming_app_data / "cursor-electron", # Older/alternate name?
            roaming_app_data / "CursorAI", # Potential new name?
        ]
        paths["cache_dirs"] = [
            local_app_data / "Cursor",
            local_app_data / "cursor-electron",
            local_app_data / "CursorAI",
            temp_dir / "Cursor",
            temp_dir / "cursor-updater",
            roaming_app_data / "Code" / "User" / "workspaceStorage", # VSCode base, check for cursor workspaces
            roaming_app_data / "Code" / "User" / "globalStorage" / "cursorai.cursor", # Specific extension storage
        ]
        paths["state_files"] = [
            home_dir / ".cursor_trial_data", # Old trial file?
            home_dir / ".cursor_license",    # Old license file?
            home_dir / ".cursor-machine-id", # Old machine ID?
            roaming_app_data / "Cursor" / "User" / "state.vscdb", # VSCode state DB
            roaming_app_data / "Cursor" / "User" / "sync", # Sync data
             roaming_app_data / "Cursor" / "storage.json", # VSCode storage metadata
             roaming_app_data / "Cursor" / "logs", # Logs directory
        ]
        # Define potential locations for the machine ID to be RECREATED
        paths["machine_id_files"] = [
             roaming_app_data / "Cursor" / "machineid" # Adjusted path based on common patterns
        ]
        # Define the location for the trial info to be RECREATED
        paths["trial_file"] = roaming_app_data / "Cursor" / "trial_info.json" # Common location

    elif system == "Darwin":  # macOS
        library = home_dir / "Library"
        app_support = library / "Application Support"
        caches = library / "Caches"
        prefs = library / "Preferences"
        saved_state = library / "Saved Application State"
        http_storage = library / "HTTPStorages"
        paths["allowed_bases"] = EXPECTED_BASES["Darwin"]

        paths["config_dirs"] = [
            app_support / "Cursor",
            app_support / "cursor-electron",
        ]
        paths["cache_dirs"] = [
            caches / "Cursor",
            caches / "cursor-electron",
            app_support / "Code" / "User" / "workspaceStorage", # VSCode base
            app_support / "Code" / "User" / "globalStorage" / "cursorai.cursor", # Specific extension storage
        ]
        paths["state_files"] = [
            prefs / "com.cursor.Cursor.plist", # Preferences file
            saved_state / "com.cursor.Cursor.savedState",
            http_storage / "com.cursor.Cursor", # Web cache/storage
            home_dir / ".cursor_trial_data",
            home_dir / ".cursor_license",
            home_dir / ".cursor-machine-id",
            app_support / "Cursor" / "User" / "state.vscdb",
            app_support / "Cursor" / "User" / "sync",
            app_support / "Cursor" / "storage.json",
            app_support / "Cursor" / "logs",
        ]
        paths["machine_id_files"] = [
            app_support / "Cursor" / "machineid"
        ]
        paths["trial_file"] = app_support / "Cursor" / "trial_info.json"

    elif system == "Linux":
        config_dir = home_dir / ".config"
        cache_dir = home_dir / ".cache"
        local_share = home_dir / ".local" / "share"
        paths["allowed_bases"] = EXPECTED_BASES["Linux"]

        paths["config_dirs"] = [
            config_dir / "Cursor",
            config_dir / "cursor-electron",
        ]
        paths["cache_dirs"] = [
            cache_dir / "Cursor",
            cache_dir / "cursor-electron",
            config_dir / "Code" / "User" / "workspaceStorage", # VSCode base
            config_dir / "Code" / "User" / "globalStorage" / "cursorai.cursor", # Specific extension storage
        ]
        paths["state_files"] = [
            local_share / "Cursor",       # Less common, but possible
            local_share / "cursor-electron",
            home_dir / ".cursor_trial_data",
            home_dir / ".cursor_license",
            home_dir / ".cursor-machine-id",
            config_dir / "Cursor" / "User" / "state.vscdb",
            config_dir / "Cursor" / "User" / "sync",
            config_dir / "Cursor" / "storage.json",
            config_dir / "Cursor" / "logs",
        ]
        paths["machine_id_files"] = [
            config_dir / "Cursor" / "machineid"
        ]
        paths["trial_file"] = config_dir / "Cursor" / "trial_info.json"

    else:
        print(f"{Fore.RED}{EMOJI['ERROR']} Unsupported OS: {system}")
        return None # Indicate failure

    # Clean up potential workspace storage (can contain many subdirs)
    # Be careful here, only remove if clearly cursor related? Maybe too risky.
    # Let's keep it commented out for now unless specifically needed and confirmed safe.
    # workspace_storage_path = paths["cache_dirs"][2] # Example: .../Code/User/workspaceStorage
    # if workspace_storage_path.exists():
    #     for item in workspace_storage_path.iterdir():
    #         # Add logic here to identify Cursor-specific workspace folders if possible
    #         pass # Placeholder

    return paths


# --- Main Reset Logic ---

def reset_cursor():
    """Performs the complete reset of Cursor AI settings, cache, and trial state."""
    home_dir = Path.home()
    os_paths = get_os_paths(home_dir)

    if not os_paths:
        return # Unsupported OS or error getting paths

    print(f"\n{Fore.CYAN}{Style.BRIGHT}===== Cursor AI Reset Tool ====={Style.NORMAL}")
    print(f"{Fore.RED}{Style.BRIGHT}{EMOJI['WARNING']} WARNING: This tool will attempt to completely reset Cursor AI.{Style.NORMAL}")
    print(f"{Fore.YELLOW}This involves deleting configuration, cache, state, and license/trial files.")
    print(f"{Fore.YELLOW}Make sure Cursor AI is not running before proceeding.")
    print(f"{Fore.YELLOW}Your settings and history will be lost. This action is irreversible.")
    print(f"{Fore.YELLOW}It attempts to reset your trial, but this is not guaranteed to work long-term.")
    print(f"{Fore.YELLOW}{Style.DIM}Paths targeted for deletion are within standard application data locations:")
    print(f"{Style.DIM}  {', '.join(os_paths['allowed_bases'])} relative to {home_dir}")

    try:
        choice = input(f"\n{Fore.RED}{Style.BRIGHT}Confirm Cursor AI reset? (y/N): {Style.RESET_ALL}").strip().lower()
        if choice != 'y':
            print(f"\n{Fore.CYAN}Reset cancelled by user.{Style.RESET_ALL}")
            return
    except EOFError: # Handle case where input stream is closed (e.g., piping)
         print(f"\n{Fore.RED}Input closed unexpectedly. Reset cancelled.{Style.RESET_ALL}")
         return


    print(f"\n{Fore.CYAN}{EMOJI['RESET']} Starting Cursor AI reset for {platform.system()}...{Style.RESET_ALL}")

    # --- Deletion Phase ---
    print(f"\n{Style.BRIGHT}--- Removing Configuration Directories ---{Style.NORMAL}")
    for path in os_paths["config_dirs"]:
        remove_path(path, home_dir, os_paths["allowed_bases"])

    print(f"\n{Style.BRIGHT}--- Removing Cache Directories ---{Style.NORMAL}")
    for path in os_paths["cache_dirs"]:
        remove_path(path, home_dir, os_paths["allowed_bases"])

    print(f"\n{Style.BRIGHT}--- Removing State & Other Files ---{Style.NORMAL}")
    for path in os_paths["state_files"]:
        remove_path(path, home_dir, os_paths["allowed_bases"])

    # --- Creation Phase ---
    print(f"\n{Style.BRIGHT}--- Recreating Identifiers and Trial Info ---{Style.NORMAL}")
    print(f"{Fore.YELLOW}{EMOJI['INFO']} Attempting to create new identifiers to reset trial status...")

    # Create new machine ID(s)
    if not os_paths["machine_id_files"]:
         print(f"{Fore.YELLOW}{EMOJI['INFO']} No specific machine ID file path defined for recreation on this OS.")
    else:
        for path in os_paths["machine_id_files"]:
             # Check if the parent directory *should* exist after cleaning config dirs
             # This assumes the ID lives inside one of the main config dirs.
             # If the config dir was deleted, recreate it minimally.
             if path.parent.exists() or any(parent == path.parent for parent in os_paths["config_dirs"]):
                 create_new_machine_id(path)
             else:
                 print(f"{Fore.YELLOW}{EMOJI['INFO']} Skipping machine ID creation for {path} as parent directory doesn't seem related to standard config paths.")


    # Create new trial info file
    if os_paths["trial_file"]:
         # Similar logic: ensure the parent dir is reasonable before creating
        if os_paths["trial_file"].parent.exists() or any(parent == os_paths["trial_file"].parent for parent in os_paths["config_dirs"]):
            create_new_trial_info(os_paths["trial_file"])
        else:
             print(f"{Fore.YELLOW}{EMOJI['INFO']} Skipping trial info creation for {os_paths['trial_file']} as parent directory doesn't seem related to standard config paths.")
    else:
         print(f"{Fore.YELLOW}{EMOJI['INFO']} No specific trial info file path defined for recreation on this OS.")


    # --- Completion Message ---
    print(f"\n{Fore.GREEN}{Style.BRIGHT}{EMOJI['SUCCESS']} Cursor AI reset process completed!{Style.NORMAL}")
    print(f"{Fore.CYAN}{EMOJI['INFO']} Files and directories related to Cursor AI have been removed.")
    print(f"{Fore.CYAN}{EMOJI['INFO']} A new machine ID and trial information file have been attempted.")
    print(f"{Fore.YELLOW}{EMOJI['WARNING']} You may need to restart Cursor AI, or potentially reinstall it, for changes to take full effect.")
    print(f"{Fore.YELLOW}Enjoy your potentially refreshed trial period!")

# --- Main Execution ---

if __name__ == "__main__":
    try:
        reset_cursor()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.RED}{EMOJI['WARNING']} Process interrupted by user.{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}{Style.BRIGHT}{EMOJI['ERROR']} An unexpected critical error occurred: {e}{Style.RESET_ALL}")
        import traceback
        print(f"{Fore.RED}{Style.DIM}")
        traceback.print_exc() # Print detailed traceback for debugging
        print(Style.RESET_ALL)
        sys.exit(1)
    finally:
        # Add a pause so the user can read the output when run directly
        input(f"\n{Fore.CYAN}Press Enter to exit...{Style.RESET_ALL}")
