import sys
import os
import json
import glob
import shutil
import subprocess
from pathlib import Path

def error_exit(message):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)

def run_command(cmd, cwd=None):
    executable = shutil.which(cmd[0])
    if executable is None:
        error_exit(f"Command not found: {cmd[0]}")
    
    cmd_resolved = [executable] + cmd[1:]
    
    try:
        subprocess.check_call(cmd_resolved, cwd=cwd)
    except subprocess.CalledProcessError as e:
        error_exit(f"Command failed with exit code {e.returncode}: {' '.join(cmd)}")

def get_framework_path(package_name):
    cmd = ["cargo", "metadata", "--format-version", "1"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
    except subprocess.CalledProcessError:
        error_exit("Failed to run 'cargo metadata'.")
    except json.JSONDecodeError:
        error_exit("Failed to parse 'cargo metadata' output.")
    for pkg in metadata.get("packages", []):
        if pkg.get("name") == package_name:
            manifest_path = pkg.get("manifest_path")
            if manifest_path:
                return Path(manifest_path).parent
    return None

def find_user_lib(search_dir, pattern):
    search_path = search_dir / pattern
    files = glob.glob(str(search_path))
    
    if not files:
        return None
    
    return Path(files[0]).resolve()

def main():
    PACKAGE_NAME = "dosoxide"
    LIB_PATTERN = "libdosoxide_app*.a"
    LIB_PATTERN2 = "libdosoxide*"
    LIB_PATTERN3 = "dosoxide*.d"
    OUTPUT_NAME = "PROGRAM.EXE"
    
    framework_path = get_framework_path(PACKAGE_NAME)
    
    if not framework_path:
        error_exit(f"Could not find '{PACKAGE_NAME}' in dependencies.")
    
    print(f"Framework found at: {framework_path}")

    target_spec = framework_path / "i386-dos.json"
    
    deps_dir = Path("target") / "i386-dos" / "release" / "deps"
    # first we should delete the deps folder as I noticed that sometimes old builds can cause issues
    # but deleting the entire folder causes core rebuilds which is very slow, so we will just delete the files matching our pattern
    for file in glob.glob(str(deps_dir / LIB_PATTERN2)):
        os.remove(file)
    for file in glob.glob(str(deps_dir / LIB_PATTERN3)):
        os.remove(file)
    cargo_cmd = [
        "cargo", "+nightly", "build", "--release",
        "-Z", "build-std=core,alloc",
        "-Z", "build-std-features=compiler-builtins-mem",
        "-Z", "json-target-spec",
        "--target", str(target_spec)
    ]
    
    run_command(cargo_cmd)

    user_lib = find_user_lib(deps_dir, LIB_PATTERN)
    
    if not user_lib:
        error_exit(f"Could not find library matching '{LIB_PATTERN}' in {deps_dir}")

    staging_dir = Path("staging")
    bin_dir = Path("bin")
    
    staging_dir.mkdir(exist_ok=True)
    bin_dir.mkdir(exist_ok=True)

    header_s = framework_path / "asm" / "header.s"
    start_s = framework_path / "asm" / "start.s"
    linker_ld = framework_path / "linker.ld"

    # clang -target i386-unknown-none -c header.s -o header.o
    run_command([
        "clang", "-target", "i386-unknown-none", 
        "-c", str(header_s.resolve()), 
        "-o", "header.o"
    ], cwd=staging_dir)

    # ld.lld --oformat binary -o header.bin header.o
    run_command([
        "ld.lld", "--oformat", "binary", 
        "-o", "header.bin", "header.o"
    ], cwd=staging_dir)

    # clang -target i386-unknown-none -m32 -c start.s -o start.o
    run_command([
        "clang", "-target", "i386-unknown-none", 
        "-m32", 
        "-c", str(start_s.resolve()), 
        "-o", "start.o"
    ], cwd=staging_dir)

    # ld.lld -T linker.ld --oformat binary -nmagic --gc-sections -o body.bin start.o user_lib
    run_command([
        "ld.lld", 
        "-T", str(linker_ld.resolve()),
        "--oformat", "binary",
        "-nmagic",
        "--gc-sections",
        "-o", "body.bin",
        "start.o", 
        str(user_lib)
    ], cwd=staging_dir)

    output_file = staging_dir / OUTPUT_NAME
    header_bin = staging_dir / "header.bin"
    body_bin = staging_dir / "body.bin"

    with open(output_file, "wb") as outfile:
        with open(header_bin, "rb") as infile:
            outfile.write(infile.read())
        with open(body_bin, "rb") as infile:
            outfile.write(infile.read())

    os.remove(staging_dir / "header.o")
    os.remove(staging_dir / "start.o")
    os.remove(header_bin)
    os.remove(body_bin)

    final_dest = bin_dir / OUTPUT_NAME
    shutil.move(str(output_file), str(final_dest))

    try:
        os.rmdir(staging_dir)
    except OSError:
        pass
    print(f"Build successful! Output: {final_dest}")

if __name__ == "__main__":
    main()
