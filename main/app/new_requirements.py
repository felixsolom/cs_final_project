import subprocess

def get_installed_packages():
    """Returns a set of installed packages without versions (for requirements.in)."""
    result = subprocess.run(["pip", "freeze"], capture_output=True, text=True)
    return {line.split("==")[0] for line in result.stdout.splitlines()}

def get_existing_requirements(file_path="requirements.in"):
    """Reads requirements.in and returns a set of packages (without versions)."""
    try:
        with open(file_path, "r") as file:
            return {line.strip() for line in file if line.strip()}
    except FileNotFoundError:
        return set()

def update_requirements_in(file_path="requirements.in"):
    """Updates requirements.in with new dependencies, avoiding duplicates."""
    installed_packages = get_installed_packages()
    existing_packages = get_existing_requirements(file_path)

    all_packages = sorted(installed_packages | existing_packages)

    with open(file_path, "w") as file:
        file.write("\n".join(all_packages) + "\n")

    print(f"Updated {file_path} with {len(all_packages)} dependencies.")

if __name__ == "__main__":
    update_requirements_in()