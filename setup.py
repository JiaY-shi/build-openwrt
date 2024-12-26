#!/usr/bin/env python3

import os
import sys
import yaml
import logging
from pathlib import Path
from shutil import rmtree
from subprocess import run, CalledProcessError
from os import getenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# 结束运行
def die(msg: str):
    """Quit script with error message."""
    logger.error(msg)
    raise SystemExit(1)

# 使用帮助
def usage(code: int = 0):
    """Print script usage."""
    print(f"""Usage: {sys.argv[0]} <profile>
    
    build           Automatically build device firmware
    config          Generate '.config' file settings
    feeds           Generate 'feeds.conf' file
    clean           Remove feeds before setup
    help            Print this message
    """)
    sys.exit(code)


def load_yaml(fname: str, profile: dict, include=True):
    """Load YAML profile configuration."""
    file_path = Path(f"{fname}.yml").absolute()
    if not file_path.exists():
        die(f"Profile {fname} not found")

    with open(file_path, "r") as f:
        new = yaml.safe_load(f)
    
    for n, value in new.items():
        if n in {"repo", "branch", "clone_dir", "device", "target", "subtarget"}:
            if profile.get(n):
                die(f"Duplicate tag found: {n}")
            profile[n] = value
        elif n == "description":
            profile.setdefault("description", []).append(value)
        elif n == "packages":
            profile.setdefault("packages", []).extend(value)
        elif n == "diffconfig":
            profile["diffconfig"] += value
        elif n == "feeds":
            for feed in value:
                if not feed.get("name") or (not feed.get("uri") and not feed.get("path")):
                    die(f"Found bad feed: {feed}")
                profile.setdefault("feeds", {})[feed["name"]] = feed

    if "include" in new and include:
        for included_profile in new["include"]:
            profile = load_yaml(included_profile, profile)
    
    return profile


def clean_tree(clone_dir=""):
    if clone_dir == "":
        rmtree("work", ignore_errors=True)
    else:
        logger.info("Cleaning tree")
        for path in ["tmp", "packages/feeds", "tmp/", ".git/rebase-apply"]:
            rmtree(clone_dir +"/" +path, ignore_errors=True)

        for file in [Path(clone_dir +"/feeds.conf"), Path(clone_dir +"/.config")]:
            if file.is_file():
                file.unlink()


def generate_feeds(feeds={}):
    """Generate feeds.conf from profile."""
    feeds_output = ""
    for feed in feeds.values():
        try:
            if all(k in feed for k in ("branch", "revision", "path", "tag")):
                die(f"Please specify either a branch, a revision or a path: {feed}")
            if "path" in feed:
                feeds_output += f"{feed.get('method', 'src-link')} {feed['name']} {feed['path']}\n"
            elif "revision" in feed:
                feeds_output += f"{feed.get('method', 'src-link')} {feed['name']} {feed['uri']}^{feed['revision']}\n"
            elif "tag" in feed:
                feeds_output += f"{feed.get('method', 'src-link')} {feed['name']} {feed['uri']};{feed['tag']}\n"
            elif "branch" in feed:
                feeds_output += f"{feed.get('method', 'src-link')} {feed['name']} {feed['uri']};{feed.get('branch')}\n"
            else:
                feeds_output += f"{feed.get('method', 'src-link')} {feed['name']} {feed['uri']}\n"
        except Exception as e:
            logger.error(f"Badly configured feed: {feed}. Error: {e}")
    return feeds_output


def generate_config(target:str,subtarget:str,device:str,packages = [],diffconfig = ""):
    """Generate OpenWrt configuration from profile."""
    config_output = f"""CONFIG_TARGET_{target}=y
CONFIG_TARGET_{target}_{subtarget}=y
CONFIG_TARGET_{target}_{subtarget}_DEVICE_{device}=y
"""
    config_output += diffconfig
    for package in packages:
        config_output += f"CONFIG_PACKAGE_{package}=y\n"
    return config_output


def write_file(file: str, context: str):
    """Write content to a file."""
    Path(file).write_text(context)


def setup_feeds(work_dir:str,feeds={}):
    """Set up feeds by writing to feeds.conf and installing them."""
    feed_file = work_dir + "/feeds.conf"
    write_file(feed_file, generate_feeds(feeds))

    if run(["./scripts/feeds", "update","-a"], cwd=work_dir).returncode:
        die("Error updating feeds")

    if run(["./scripts/feeds", "install", "-f","-a"], cwd=work_dir).returncode:
        die("Error installing packages")

def setup_config(work_dir:str,target:str,subtarget:str,device:str,packages = [],diffconfig = ""):
    """Set up configuration file."""
    config_file = work_dir + "/.config"
    write_file(config_file, generate_config(target,subtarget,device,packages,diffconfig))
    
    run(["make", "defconfig"], cwd=work_dir, check=True)


def clone_tree(work_dir:str,repo:str,branch:str):
    """Clone the OpenWrt tree if not already cloned."""
    makefile = Path(work_dir) / "Makefile"
    if makefile.exists():
        logger.info("### OpenWrt checkout is already present.")
        return 1

    logger.info("### Cloning tree")
    try:
        run(["git", "clone", "-b",branch, repo,work_dir], check=True)
        logger.info("### Clone done")
        return 0
    except CalledProcessError:
        logger.error("### Cloning the tree failed")
        return 1


def build(work_path: str):
    """Build OpenWrt with the appropriate number of threads."""
    try:
        c = os.cpu_count()
        run(["make", "-j", str(c + 1), "V=s"], cwd=work_path, check=True)
    except CalledProcessError:
        logger.error("Build failed")


def check_param(profile):
    fields = ["repo", "branch", "clone_dir", "device", "target", "subtarget"]
    for field in fields:
        if profile.get(field) == "":
            die(f"Please check the '{field}' field in the profile file")
        

if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage(1)

    profile = {"repo": "", "branch": "", "clone_dir": "", "device": "", "packages": [], "description": [], "diffconfig": "", "feeds": {}}
    profile = load_yaml(sys.argv[2], profile)
    
    check_param(profile)
    
    work_dir = "work/" + profile.get("clone_dir")

    if sys.argv[1] == "feeds":
        logger.info("################### feeds.conf ########################")
        print(generate_feeds(profile.get("feeds")))
        logger.info("###################### end ############################")
        sys.exit(0)
    elif sys.argv[1] == "config":
        logger.info("################### .config ########################")
        print(generate_config(profile.get("target"),profile.get("subtarget"),profile.get("device"),profile.get("packages"),profile.get("diffconfig")))
        logger.info("##################### end ##########################")
        sys.exit(0)
    elif sys.argv[1] == "clean":
        clean_tree(profile.get("clone_dir"))
        sys.exit(0)
    elif sys.argv[1] == "build":
        if Path(work_dir).exists():
            if run(["git", "pull"], cwd=work_dir).returncode:
                die("Error updating git tree")
        else:
            clone_tree(work_dir,profile["repo"],profile["branch"])

        if not Path(work_dir + "/feeds.conf").exists():
            setup_feeds(work_dir,profile.get("feeds",{}))
        # 
        setup_config(work_dir,profile.get("target"),profile.get("subtarget"),profile.get("device"),profile.get("packages"),profile.get("diffconfig"))
        # 
        build(work_dir)